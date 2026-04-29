"""
RED: tests for drive_zip_streamer.DriveZipStreamer

All tests fail until src/drive_zip_streamer.py is implemented.
Tests use a mock HTTP client — no real Drive API calls.
"""
import io
import zipfile
import pytest
from unittest.mock import MagicMock, patch
from src.drive_zip_streamer import DriveZipStreamer, ZipEntry


def _build_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture()
def fake_zip() -> bytes:
    return _build_zip({
        "Photos/2021/IMG_0001.jpg": b"fake-jpeg-bytes-001",
        "Photos/2021/IMG_0001.jpg.json": b'{"url":"https://photos.google.com/photo/AAA"}',
        "Photos/2021/IMG_0002.jpg": b"fake-jpeg-bytes-002",
        "Photos/2021/IMG_0002.jpg.json": b'{"url":"https://photos.google.com/photo/BBB"}',
    })


def _make_streamer(zip_bytes: bytes) -> DriveZipStreamer:
    """Return a DriveZipStreamer with a mock HTTP client backed by zip_bytes."""
    mock_http = MagicMock()

    def fake_request(url, headers=None, **kwargs):
        resp = MagicMock()
        range_header = (headers or {}).get("Range", "")
        if range_header.startswith("bytes="):
            start, end = range_header[6:].split("-")
            start, end = int(start), int(end)
            resp.content = zip_bytes[start:end + 1]
            resp.status_code = 206
        else:
            resp.content = zip_bytes
            resp.status_code = 200
        resp.headers = {"Content-Length": str(len(zip_bytes))}
        return resp

    mock_http.get = fake_request
    return DriveZipStreamer(http_client=mock_http, file_id="fake-file-id")


def test_list_entries_returns_zip_entries(fake_zip):
    streamer = _make_streamer(fake_zip)
    entries = list(streamer.list_entries())
    assert len(entries) == 4


def test_entries_have_correct_names(fake_zip):
    streamer = _make_streamer(fake_zip)
    names = {e.name for e in streamer.list_entries()}
    assert "Photos/2021/IMG_0001.jpg" in names
    assert "Photos/2021/IMG_0001.jpg.json" in names


def test_entry_read_returns_correct_bytes(fake_zip):
    streamer = _make_streamer(fake_zip)
    entry = next(e for e in streamer.list_entries() if e.name == "Photos/2021/IMG_0001.jpg")
    assert entry.read() == b"fake-jpeg-bytes-001"


def test_entry_is_image_true_for_jpg(fake_zip):
    streamer = _make_streamer(fake_zip)
    entry = next(e for e in streamer.list_entries() if e.name.endswith(".jpg"))
    assert entry.is_image is True


def test_entry_is_image_false_for_json(fake_zip):
    streamer = _make_streamer(fake_zip)
    entry = next(e for e in streamer.list_entries() if e.name.endswith(".json"))
    assert entry.is_image is False


def test_entry_is_sidecar_true_for_json(fake_zip):
    streamer = _make_streamer(fake_zip)
    entry = next(e for e in streamer.list_entries() if e.name.endswith(".json"))
    assert entry.is_sidecar is True


def test_does_not_read_full_zip_upfront(fake_zip):
    """DriveZipStreamer must not issue a full-file HTTP GET during list_entries."""
    mock_http = MagicMock()
    full_reads = []

    def fake_request(url, headers=None, **kwargs):
        resp = MagicMock()
        range_header = (headers or {}).get("Range", "")
        if not range_header:
            full_reads.append(url)
        resp.content = fake_zip if not range_header else fake_zip
        resp.status_code = 200 if not range_header else 206
        resp.headers = {"Content-Length": str(len(fake_zip))}
        if range_header.startswith("bytes="):
            start, end = range_header[6:].split("-")
            resp.content = fake_zip[int(start):int(end) + 1]
        return resp

    mock_http.get = fake_request
    streamer = DriveZipStreamer(http_client=mock_http, file_id="fake-file-id")
    list(streamer.list_entries())
    assert len(full_reads) == 0, "Should not have issued a full-file GET"
