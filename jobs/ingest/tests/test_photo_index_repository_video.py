"""Tests for youtube_video_id support in PhotoIndexRepository."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from src.photo_index_repository import PhotoIndexRepository, PhotoDoc


@pytest.fixture()
def mock_db():
    return MagicMock()


@pytest.fixture()
def repo(mock_db):
    return PhotoIndexRepository(db=mock_db)


def _image_doc() -> PhotoDoc:
    return PhotoDoc(
        google_photos_id="IMG001",
        filename="IMG_0001.jpg",
        taken_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
        preview_gcs_path="previews/IMG001.webp",
        original_gcs_path="originals/IMG001.jpg",
        width=1280,
        height=960,
        latitude=None,
        longitude=None,
        media_type="photo",
    )


def _video_doc() -> PhotoDoc:
    return PhotoDoc(
        google_photos_id="VID001",
        filename="VID_0001.mp4",
        taken_at=datetime(2021, 7, 4, tzinfo=timezone.utc),
        preview_gcs_path=None,
        original_gcs_path=None,
        width=None,
        height=None,
        latitude=None,
        longitude=None,
        media_type="video",
        youtube_video_id="yt_abc123",
    )


def test_upsert_video_writes_youtube_video_id(repo, mock_db):
    repo.upsert(_video_doc())
    written = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert written["youtube_video_id"] == "yt_abc123"


def test_upsert_video_omits_original_gcs_path(repo, mock_db):
    repo.upsert(_video_doc())
    written = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert "original_gcs_path" not in written


def test_upsert_image_writes_original_gcs_path(repo, mock_db):
    repo.upsert(_image_doc())
    written = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert written["original_gcs_path"] == "originals/IMG001.jpg"


def test_upsert_image_omits_youtube_video_id(repo, mock_db):
    repo.upsert(_image_doc())
    written = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert "youtube_video_id" not in written
