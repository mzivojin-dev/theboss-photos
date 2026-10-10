"""
Matches media in Takeout Archives to their Sidecars and hands each pair to the indexer.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from .drive_zip_streamer import DriveZipStreamer, ZipEntry
from .index_outcome import IndexResult, Outcome
from .ingestion_ledger import UNKNOWN_EXPORT, IngestionLedger, Problem, export_of, exported_at, year_of
from .sidecar_index import SidecarIndex
from .sidecar_parser import PhotoMetadata, parse as parse_sidecar

log = logging.getLogger(__name__)

# Each Sidecar read is ~1s of Drive round trips; read them concurrently. Stays within
# the requests.Session default pool of 10 connections.
SIDECAR_READ_WORKERS = 8

# Media is indexed concurrently too, but a file is held in memory whole (briefly both
# compressed and decompressed) and the Cloud Run job has 2 GiB, so the total size of
# files in flight is capped: photos run in parallel, large videos effectively one at a time.
MEDIA_WORKERS = 6
MEDIA_BYTES_IN_FLIGHT = 512 * 1024 * 1024

# A run of failures this long means a systemic problem (expired credentials, a missing
# bucket, Firestore permissions) rather than a bad file, so the run stops.
MAX_CONSECUTIVE_FAILURES = 10


class _FailureStreak:
    def __init__(self, limit: int):
        self._limit = limit
        self._count = 0
        self._lock = threading.Lock()

    def record(self, result: IndexResult) -> None:
        with self._lock:
            if self._count >= self._limit:
                return  # once tripped, stays tripped: a success still in flight can't cancel the abort
            self._count = self._count + 1 if result.outcome is Outcome.FAILED else 0

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._count >= self._limit


class _ByteBudget:
    def __init__(self, limit: int):
        self._limit = limit
        self._used = 0
        self._changed = threading.Condition()

    @contextmanager
    def hold(self, size: int) -> Iterator[None]:
        size = min(size, self._limit)  # a file larger than the whole budget runs alone
        with self._changed:
            self._changed.wait_for(lambda: self._used + size <= self._limit)
            self._used += size
        try:
            yield
        finally:
            with self._changed:
                self._used -= size
                self._changed.notify_all()


@dataclass
class TakeoutArchive:
    file_id: str
    name: str
    streamer: DriveZipStreamer


def ingest_archives(
    archives: list[TakeoutArchive],
    index_media: Callable[[ZipEntry, PhotoMetadata], IndexResult],
    archive_fully_ingested: Callable[[TakeoutArchive], None],
    ledger: Optional[IngestionLedger] = None,
) -> None:
    # Takeout splits an export across archives, and a media file's Sidecar is often in a
    # different archive than the media itself, so collect every archive's Sidecars first.
    sidecar_entries = [
        entry for archive in archives for entry in archive.streamer.list_entries() if entry.is_sidecar
    ]
    log.info("Reading %d sidecars from %d archive(s)", len(sidecar_entries), len(archives))
    with ThreadPoolExecutor(SIDECAR_READ_WORKERS) as pool:
        sidecars = SidecarIndex(dict(zip(
            (entry.name for entry in sidecar_entries),
            pool.map(lambda entry: entry.read(), sidecar_entries),
        )))

    if ledger is not None:
        _record_exports(ledger, archives)
    unresolved = ledger.unresolved() if ledger is not None else set()

    def record_problem(archive: TakeoutArchive, entry: ZipEntry, kind: str, reason: str,
                       metadata: Optional[PhotoMetadata] = None) -> None:
        if ledger is not None:
            ledger.record_problem(Problem(
                export=export_of(archive.name), archive=archive.name, path=entry.name, kind=kind,
                reason=reason, taken_at=metadata.taken_at if metadata else None,
            ))

    failure_streak = _FailureStreak(MAX_CONSECUTIVE_FAILURES)

    for archive in archives:
        log.info("Processing archive: %s (%s)", archive.name, archive.file_id)
        no_sidecar = 0
        bad_sidecar = 0
        matched: list[tuple[ZipEntry, PhotoMetadata]] = []

        for entry in archive.streamer.list_entries():
            if not entry.is_image and not entry.is_video:
                continue

            sidecar_bytes = sidecars.find(entry.name)
            if sidecar_bytes is None:
                log.warning("No sidecar for %s — skipping", entry.name)
                no_sidecar += 1
                record_problem(archive, entry, "no_sidecar", "No Sidecar found")
                continue

            try:
                metadata = parse_sidecar(sidecar_bytes)
            except ValueError as e:
                log.warning("Sidecar parse error for %s: %s — skipping", entry.name, e)
                bad_sidecar += 1
                record_problem(archive, entry, "bad_sidecar", str(e))
                continue

            matched.append((entry, metadata))

        budget = _ByteBudget(MEDIA_BYTES_IN_FLIGHT)

        def index_within_budget(item: tuple[ZipEntry, PhotoMetadata]) -> IndexResult | None:
            entry, metadata = item
            with budget.hold(entry.size):
                if failure_streak.tripped:
                    return None  # the run is aborting; don't start more work
                result = index_media(entry, metadata)
            failure_streak.record(result)
            return result

        with ThreadPoolExecutor(MEDIA_WORKERS) as pool:
            results = list(pool.map(index_within_budget, matched))
        if failure_streak.tripped:
            raise RuntimeError(
                f"Aborting ingestion: {MAX_CONSECUTIVE_FAILURES} media files in a row failed to index "
                "(see the warnings above); this looks like a systemic problem such as credentials or permissions"
            )
        for (entry, metadata), result in zip(matched, results):
            if result is None:
                continue
            if result.outcome is Outcome.FAILED:
                record_problem(archive, entry, "failed", result.reason or "", metadata)
            elif ledger is not None and (export_of(archive.name), entry.name) in unresolved:
                ledger.resolve(export_of(archive.name), entry.name)
        counts = {outcome: sum(result.outcome is outcome for result in results) for outcome in Outcome}

        # Keep an archive with unmatched, unparseable or failed media so deleting it can't lose those files.
        keep = no_sidecar or bad_sidecar or counts[Outcome.FAILED]
        log.log(
            logging.WARNING if keep else logging.INFO,
            "%s: %d indexed, %d already indexed, %d no Sidecar, %d bad Sidecar, %d failed — %s",
            archive.name, counts[Outcome.INDEXED], counts[Outcome.ALREADY_INDEXED], no_sidecar,
            bad_sidecar, counts[Outcome.FAILED], "kept" if keep else "fully ingested",
        )
        if not keep:
            archive_fully_ingested(archive)


def _record_exports(ledger: IngestionLedger, archives: list[TakeoutArchive]) -> None:
    """Merge what this run saw of each export into the ledger: its archives and its `Photos from YYYY` years."""
    names: dict[str, set[str]] = {}
    years: dict[str, set[int]] = {}
    for archive in archives:
        export = export_of(archive.name)
        names.setdefault(export, set()).add(archive.name)
        years.setdefault(export, set()).update(
            year for entry in archive.streamer.list_entries() if (year := year_of(entry.name)) is not None
        )
    for export in names:
        if export == UNKNOWN_EXPORT:
            continue  # an archive not named like a Takeout export says nothing about what was exported
        ledger.record_export(export, exported_at(export), names[export], years[export])
