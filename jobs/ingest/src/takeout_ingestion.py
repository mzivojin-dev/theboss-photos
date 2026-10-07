"""
Matches media in Takeout Archives to their Sidecars and hands each pair to the indexer.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from .drive_zip_streamer import DriveZipStreamer, ZipEntry, find_matching_sidecar
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
    index_media: Callable[[ZipEntry, PhotoMetadata], None],
    archive_fully_ingested: Callable[[TakeoutArchive], None],
) -> None:
    # Takeout splits an export across archives, and a media file's Sidecar is often in a
    # different archive than the media itself, so collect every archive's Sidecars first.
    sidecar_entries = [
        entry for archive in archives for entry in archive.streamer.list_entries() if entry.is_sidecar
    ]
    log.info("Reading %d sidecars from %d archive(s)", len(sidecar_entries), len(archives))
    with ThreadPoolExecutor(SIDECAR_READ_WORKERS) as pool:
        sidecars = dict(zip(
            (entry.name for entry in sidecar_entries),
            pool.map(lambda entry: entry.read(), sidecar_entries),
        ))

    for archive in archives:
        log.info("Processing archive: %s (%s)", archive.name, archive.file_id)
        skipped = 0
        matched: list[tuple[ZipEntry, PhotoMetadata]] = []

        for entry in archive.streamer.list_entries():
            if not entry.is_image and not entry.is_video:
                continue

            # Match sidecar by canonical filename, ignoring case and duplicate suffixes.
            sidecar_bytes = find_matching_sidecar(entry.name.split("/")[-1], sidecars)
            if sidecar_bytes is None:
                log.warning("No sidecar for %s — skipping", entry.name)
                skipped += 1
                continue

            try:
                metadata = parse_sidecar(sidecar_bytes)
            except ValueError as e:
                log.warning("Sidecar parse error for %s: %s — skipping", entry.name, e)
                skipped += 1
                continue

            matched.append((entry, metadata))

        budget = _ByteBudget(MEDIA_BYTES_IN_FLIGHT)

        def index_within_budget(item: tuple[ZipEntry, PhotoMetadata]) -> None:
            entry, metadata = item
            with budget.hold(entry.size):
                index_media(entry, metadata)

        with ThreadPoolExecutor(MEDIA_WORKERS) as pool:
            list(pool.map(index_within_budget, matched))  # list() re-raises the first failure

        # Keep an archive with skipped media so deleting it can't lose those files.
        if skipped:
            log.warning("Keeping archive %s: %d media file(s) skipped", archive.name, skipped)
        else:
            archive_fully_ingested(archive)
