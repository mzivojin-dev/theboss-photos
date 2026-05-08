"""Tests for main.run() — verifies Cloud Run video/image branching behaviour."""
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import pytest

from src.photo_index_repository import PhotoDoc


_TAKEN_AT = datetime(2023, 7, 15, tzinfo=timezone.utc)


def _sidecar_metadata():
    meta = MagicMock()
    meta.google_photos_id = "PHOTO_ID_001"
    meta.taken_at = _TAKEN_AT
    meta.latitude = None
    meta.longitude = None
    return meta


def _zip_entry(name, is_image=False, is_video=False, is_sidecar=False, data=b"bytes"):
    entry = MagicMock()
    entry.name = name
    entry.is_image = is_image
    entry.is_video = is_video
    entry.is_sidecar = is_sidecar
    entry.read.return_value = data
    return entry


@pytest.fixture()
def env_vars(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("PREVIEWS_BUCKET", "previews-bucket")
    monkeypatch.setenv("ORIGINALS_BUCKET", "originals-bucket")
    monkeypatch.setenv("DRIVE_FOLDER_ID", "drive-folder-id")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN_SECRET", "yt-refresh-token-secret")


@pytest.fixture()
def mock_gcp():
    with (
        patch("src.main.google_auth_default") as mock_auth,
        patch("src.main.build") as mock_build,
        patch("src.main.storage.Client") as mock_storage,
        patch("src.main.firestore.Client") as mock_firestore,
    ):
        mock_creds = MagicMock()
        mock_creds.token = "tok"
        mock_auth.return_value = (mock_creds, None)

        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        yield {
            "auth": mock_auth,
            "drive": mock_drive,
            "storage": mock_storage,
            "firestore": mock_firestore,
        }


def _setup_drive(mock_gcp, entries):
    """Configure the Drive mock to return one ZIP file with the given entries."""
    mock_drive = mock_gcp["drive"]
    mock_drive.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "zip-file-id", "name": "takeout.zip"}]
    }
    mock_drive.files.return_value.delete.return_value.execute.return_value = {}

    streamer_instance = MagicMock()
    streamer_instance.list_entries.return_value = entries
    return streamer_instance


# ---------------------------------------------------------------------------
# Test 1 — RED
# ---------------------------------------------------------------------------

def test_video_entry_uploads_to_youtube_and_writes_video_id(env_vars, mock_gcp):
    sidecar = _zip_entry("photo.mp4.json", is_sidecar=True, data=b'{"sidecar": true}')
    video = _zip_entry("photo.mp4", is_video=True, data=b"video-bytes")
    entries = [sidecar, video]

    streamer_instance = _setup_drive(mock_gcp, entries)

    mock_repo = MagicMock()
    mock_repo.exists.return_value = False

    mock_uploader = MagicMock()
    mock_uploader.upload.return_value = "yt-video-id-123"

    meta = _sidecar_metadata()

    with (
        patch("src.main.DriveZipStreamer", return_value=streamer_instance),
        patch("src.main.PhotoIndexRepository", return_value=mock_repo),
        patch("src.main.YouTubeUploader", return_value=mock_uploader),
        patch("src.main.parse_sidecar", return_value=meta),
    ):
        from src import main
        main.run()

    mock_uploader.upload.assert_called_once()
    _, call_kwargs = mock_uploader.upload.call_args
    assert call_kwargs.get("taken_at") == _TAKEN_AT or mock_uploader.upload.call_args[0][1] == _TAKEN_AT

    upsert_call = mock_repo.upsert.call_args[0][0]
    assert upsert_call.youtube_video_id == "yt-video-id-123"
    assert upsert_call.media_type == "video"


def test_video_entry_does_not_upload_to_originals_bucket(env_vars, mock_gcp):
    sidecar = _zip_entry("photo.mp4.json", is_sidecar=True, data=b'{"sidecar": true}')
    video = _zip_entry("photo.mp4", is_video=True, data=b"video-bytes")
    entries = [sidecar, video]

    streamer_instance = _setup_drive(mock_gcp, entries)

    mock_repo = MagicMock()
    mock_repo.exists.return_value = False
    mock_uploader = MagicMock()
    mock_uploader.upload.return_value = "yt-video-id-123"
    mock_gcs_storage = mock_gcp["storage"].return_value

    with (
        patch("src.main.DriveZipStreamer", return_value=streamer_instance),
        patch("src.main.PhotoIndexRepository", return_value=mock_repo),
        patch("src.main.YouTubeUploader", return_value=mock_uploader),
        patch("src.main.parse_sidecar", return_value=_sidecar_metadata()),
    ):
        from src import main
        main.run()

    originals = mock_gcs_storage.bucket.return_value
    originals.blob.return_value.upload_from_string.assert_not_called()


def test_image_entry_writes_preview_and_original_unchanged(env_vars, mock_gcp):
    sidecar = _zip_entry("photo.jpg.json", is_sidecar=True, data=b'{"sidecar": true}')
    image = _zip_entry("photo.jpg", is_image=True, data=b"image-bytes")
    entries = [sidecar, image]

    streamer_instance = _setup_drive(mock_gcp, entries)

    mock_repo = MagicMock()
    mock_repo.exists.return_value = False
    mock_uploader = MagicMock()

    meta = _sidecar_metadata()

    fake_preview = b"preview-bytes"

    with (
        patch("src.main.DriveZipStreamer", return_value=streamer_instance),
        patch("src.main.PhotoIndexRepository", return_value=mock_repo),
        patch("src.main.YouTubeUploader", return_value=mock_uploader),
        patch("src.main.parse_sidecar", return_value=meta),
        patch("src.main.generate_preview", return_value=fake_preview),
        patch("src.main.Image") as mock_pil,
    ):
        mock_pil.open.return_value.size = (1280, 960)
        from src import main
        main.run()

    mock_uploader.upload.assert_not_called()

    upsert_call = mock_repo.upsert.call_args[0][0]
    assert upsert_call.media_type == "photo"
    assert upsert_call.preview_gcs_path is not None
    assert upsert_call.original_gcs_path is not None
    assert upsert_call.youtube_video_id is None
