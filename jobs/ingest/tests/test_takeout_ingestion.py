"""
Tests for takeout_ingestion.ingest_archives

Google Takeout splits a large export across several Takeout Archives, and a media
file's Sidecar is often in a different archive than the media itself.
"""
import json
import subprocess
import sys
import threading
import time

import pytest

from src import takeout_ingestion
from src.index_outcome import IndexResult, Outcome
from src.takeout_ingestion import TakeoutArchive, ingest_archives
from tests.test_drive_zip_streamer import _build_zip, _make_streamer


def _sidecar(photo_id: str) -> bytes:
    return json.dumps({
        "url": f"https://photos.google.com/photo/{photo_id}",
        "photoTakenTime": {"timestamp": "1781282749"},
    }).encode()


def _archive(name: str, files: dict[str, bytes]) -> TakeoutArchive:
    return TakeoutArchive(file_id=name, name=name, streamer=_make_streamer(_build_zip(files)))


def _indexed(_=None) -> IndexResult:
    return IndexResult(Outcome.INDEXED)


def _ingest(archives: list[TakeoutArchive]) -> tuple[dict[str, str], list[str]]:
    indexed: dict[str, str] = {}
    fully_ingested: list[str] = []
    ingest_archives(
        archives,
        index_media=lambda entry, metadata: _indexed(indexed.__setitem__(entry.name, metadata.google_photos_id)),
        archive_fully_ingested=lambda archive: fully_ingested.append(archive.name),
    )
    return indexed, fully_ingested


def test_media_is_indexed_when_its_sidecar_is_in_a_later_archive():
    part1 = _archive("takeout-001.zip", {
        "Takeout/Google Photos/Photos from 2026/PXL_20260612_182549759.mp4": b"video",
    })
    part3 = _archive("takeout-003.zip", {
        "Takeout/Google Photos/Photos from 2026/PXL_20260612_182549759.mp4.supplemental-metadata.json":
            _sidecar("VID1"),
    })

    indexed, _ = _ingest([part1, part3])

    assert indexed == {"Takeout/Google Photos/Photos from 2026/PXL_20260612_182549759.mp4": "VID1"}


def test_archives_are_fully_ingested_when_sidecars_span_archives():
    part1 = _archive("takeout-001.zip", {
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg": b"jpeg",
    })
    part2 = _archive("takeout-002.zip", {
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg.supplemental-metadata.json": _sidecar("IMG1"),
    })

    _, fully_ingested = _ingest([part1, part2])

    assert fully_ingested == ["takeout-001.zip", "takeout-002.zip"]


def test_archive_with_unmatched_media_is_not_fully_ingested():
    complete = _archive("takeout-001.zip", {
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg": b"jpeg",
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg.supplemental-metadata.json": _sidecar("IMG1"),
    })
    incomplete = _archive("takeout-002.zip", {
        "Takeout/Google Photos/Photos from 2026/IMG_2.jpg": b"jpeg",
    })

    indexed, fully_ingested = _ingest([complete, incomplete])

    assert list(indexed.values()) == ["IMG1"]
    assert fully_ingested == ["takeout-001.zip"]


def test_archive_with_unparseable_sidecar_is_not_fully_ingested():
    archive = _archive("takeout-001.zip", {
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg": b"jpeg",
        "Takeout/Google Photos/Photos from 2026/IMG_1.jpg.supplemental-metadata.json": b'{"title": "x"}',
    })

    indexed, fully_ingested = _ingest([archive])

    assert indexed == {}
    assert fully_ingested == []


def _photos_archive(count: int, photo_bytes: bytes = b"jpeg") -> TakeoutArchive:
    files = {}
    for i in range(count):
        files[f"Takeout/Google Photos/Photos from 2026/IMG_{i}.jpg"] = photo_bytes
        files[f"Takeout/Google Photos/Photos from 2026/IMG_{i}.jpg.supplemental-metadata.json"] = _sidecar(f"IMG{i}")
    return _archive("takeout-001.zip", files)


def test_media_is_indexed_concurrently():
    both_in_flight = threading.Barrier(2, timeout=5)

    def index_media(entry, metadata):
        both_in_flight.wait()  # raises BrokenBarrierError if media is indexed one at a time
        return _indexed()

    ingest_archives([_photos_archive(2)], index_media, archive_fully_ingested=lambda archive: None)


def test_media_in_flight_is_capped_by_total_size(monkeypatch):
    monkeypatch.setattr(takeout_ingestion, "MEDIA_BYTES_IN_FLIGHT", 10)
    in_flight, max_in_flight, lock = 0, 0, threading.Lock()

    def index_media(entry, metadata):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return _indexed()

    fully_ingested = []
    ingest_archives([_photos_archive(4, photo_bytes=b"x" * 8)], index_media, fully_ingested.append)

    assert max_in_flight == 1, "two 8-byte files must not be in memory together under a 10-byte cap"
    assert len(fully_ingested) == 1


def test_media_larger_than_the_cap_is_still_indexed(monkeypatch):
    monkeypatch.setattr(takeout_ingestion, "MEDIA_BYTES_IN_FLIGHT", 4)
    indexed, _ = _ingest([_photos_archive(2, photo_bytes=b"x" * 50)])
    assert sorted(indexed.values()) == ["IMG0", "IMG1"]


def _photo_archive(name: str, photo_id: str) -> TakeoutArchive:
    return _archive(name, {
        f"Takeout/Google Photos/Photos from 2026/{photo_id}.jpg": b"jpeg",
        f"Takeout/Google Photos/Photos from 2026/{photo_id}.jpg.supplemental-metadata.json": _sidecar(photo_id),
    })


def test_archive_with_a_failed_file_is_kept_and_the_run_continues():
    indexed = []

    def index_media(entry, metadata):
        if metadata.google_photos_id == "BAD":
            return IndexResult(Outcome.FAILED, "OSError: boom")
        indexed.append(metadata.google_photos_id)
        return IndexResult(Outcome.INDEXED)

    fully_ingested = []
    ingest_archives(
        [_photo_archive("takeout-001.zip", "BAD"), _photo_archive("takeout-002.zip", "GOOD")],
        index_media,
        fully_ingested.append,
    )

    assert indexed == ["GOOD"]
    assert [archive.name for archive in fully_ingested] == ["takeout-002.zip"]


def _archive_of(name: str, photo_ids: list[str]) -> TakeoutArchive:
    files = {}
    for photo_id in photo_ids:
        files[f"Takeout/Google Photos/Photos from 2026/{photo_id}.jpg"] = b"jpeg"
        files[f"Takeout/Google Photos/Photos from 2026/{photo_id}.jpg.supplemental-metadata.json"] = _sidecar(photo_id)
    return _archive(name, files)


def test_ten_failures_in_a_row_abort_the_run():
    attempted = []

    def index_media(entry, metadata):
        attempted.append(metadata.google_photos_id)
        return IndexResult(Outcome.FAILED, "Forbidden: 403 permission denied")

    failing = _archive_of("takeout-001.zip", [f"BAD{i}" for i in range(30)])
    untouched = _archive_of("takeout-002.zip", ["GOOD"])

    with pytest.raises(RuntimeError, match="10 media files in a row failed"):
        ingest_archives([failing, untouched], index_media, archive_fully_ingested=lambda archive: None)

    assert "GOOD" not in attempted
    assert len(attempted) < 30, "the run must stop instead of attempting every remaining file"


def test_a_success_resets_the_failure_streak(monkeypatch):
    monkeypatch.setattr(takeout_ingestion, "MEDIA_WORKERS", 1)  # deterministic order
    photo_ids = [f"BAD{i}" for i in range(9)] + ["GOOD"] + [f"BAD{i}" for i in range(9, 18)]

    def index_media(entry, metadata):
        if metadata.google_photos_id == "GOOD":
            return IndexResult(Outcome.INDEXED)
        return IndexResult(Outcome.FAILED, "OSError: boom")

    ingest_archives([_archive_of("takeout-001.zip", photo_ids)], index_media, archive_fully_ingested=lambda archive: None)


def test_one_summary_line_is_logged_per_archive(caplog):
    outcomes = {"NEW": Outcome.INDEXED, "OLD": Outcome.ALREADY_INDEXED, "BAD": Outcome.FAILED}
    archive = _archive("takeout-001.zip", {
        **{f"Takeout/Google Photos/{photo_id}.jpg": b"jpeg" for photo_id in outcomes},
        **{f"Takeout/Google Photos/{photo_id}.jpg.supplemental-metadata.json": _sidecar(photo_id) for photo_id in outcomes},
        "Takeout/Google Photos/ORPHAN.jpg": b"jpeg",
        "Takeout/Google Photos/GARBLED.jpg": b"jpeg",
        "Takeout/Google Photos/GARBLED.jpg.supplemental-metadata.json": b"not json",
    })
    complete = _photo_archive("takeout-002.zip", "NEW2")

    with caplog.at_level("INFO", logger="src.takeout_ingestion"):
        ingest_archives(
            [archive, complete],
            lambda entry, metadata: IndexResult(outcomes.get(metadata.google_photos_id, Outcome.INDEXED)),
            archive_fully_ingested=lambda archive: None,
        )

    summaries = [record.getMessage() for record in caplog.records if ": " in record.getMessage() and " indexed, " in record.getMessage()]
    assert summaries == [
        "takeout-001.zip: 1 indexed, 1 already indexed, 1 no Sidecar, 1 bad Sidecar, 1 failed — kept",
        "takeout-002.zip: 1 indexed, 0 already indexed, 0 no Sidecar, 0 bad Sidecar, 0 failed — fully ingested",
    ]


def test_a_success_finishing_after_the_abort_does_not_cancel_it(monkeypatch):
    monkeypatch.setattr(takeout_ingestion, "MEDIA_WORKERS", 2)
    tenth_failure = threading.Event()
    failures, lock = 0, threading.Lock()

    def index_media(entry, metadata):
        nonlocal failures
        if metadata.google_photos_id == "SLOW":
            tenth_failure.wait(timeout=5)  # was already in flight when the streak tripped
            time.sleep(0.1)  # let the tenth failure be recorded first
            return IndexResult(Outcome.INDEXED)
        with lock:
            failures += 1
            if failures == 10:
                tenth_failure.set()
        return IndexResult(Outcome.FAILED, "OSError: boom")

    archive = _archive_of("takeout-001.zip", ["SLOW"] + [f"BAD{i}" for i in range(15)])

    with pytest.raises(RuntimeError, match="10 media files in a row failed"):
        ingest_archives([archive], index_media, archive_fully_ingested=lambda archive: None)


def test_ingestion_does_not_load_the_imaging_stack():
    # In a fresh interpreter, so modules other tests imported don't count.
    loaded = subprocess.run(
        [sys.executable, "-c", "import sys, src.takeout_ingestion; print(sorted(sys.modules))"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "'PIL'" not in loaded
    assert "'pillow_heif'" not in loaded
