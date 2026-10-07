"""
Tests for takeout_ingestion.ingest_archives

Google Takeout splits a large export across several Takeout Archives, and a media
file's Sidecar is often in a different archive than the media itself.
"""
import json
import threading
import time

from src import takeout_ingestion
from src.takeout_ingestion import TakeoutArchive, ingest_archives
from tests.test_drive_zip_streamer import _build_zip, _make_streamer


def _sidecar(photo_id: str) -> bytes:
    return json.dumps({
        "url": f"https://photos.google.com/photo/{photo_id}",
        "photoTakenTime": {"timestamp": "1781282749"},
    }).encode()


def _archive(name: str, files: dict[str, bytes]) -> TakeoutArchive:
    return TakeoutArchive(file_id=name, name=name, streamer=_make_streamer(_build_zip(files)))


def _ingest(archives: list[TakeoutArchive]) -> tuple[dict[str, str], list[str]]:
    indexed: dict[str, str] = {}
    fully_ingested: list[str] = []
    ingest_archives(
        archives,
        index_media=lambda entry, metadata: indexed.__setitem__(entry.name, metadata.google_photos_id),
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

    fully_ingested = []
    ingest_archives([_photos_archive(4, photo_bytes=b"x" * 8)], index_media, fully_ingested.append)

    assert max_in_flight == 1, "two 8-byte files must not be in memory together under a 10-byte cap"
    assert len(fully_ingested) == 1


def test_media_larger_than_the_cap_is_still_indexed(monkeypatch):
    monkeypatch.setattr(takeout_ingestion, "MEDIA_BYTES_IN_FLIGHT", 4)
    indexed, _ = _ingest([_photos_archive(2, photo_bytes=b"x" * 50)])
    assert sorted(indexed.values()) == ["IMG0", "IMG1"]
