"""
RED: tests for photo_index_repository.PhotoIndexRepository

All tests fail until src/photo_index_repository.py is implemented.
Uses unittest.mock to simulate Firestore — no emulator required for unit tests.
Integration tests against the real emulator can be added separately.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, call
from src.photo_index_repository import PhotoIndexRepository, PhotoDoc


@pytest.fixture()
def mock_db():
    return MagicMock()


@pytest.fixture()
def repo(mock_db):
    return PhotoIndexRepository(db=mock_db)


def _doc(google_photos_id="AAA") -> PhotoDoc:
    return PhotoDoc(
        google_photos_id=google_photos_id,
        filename="IMG_0001.jpg",
        taken_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
        preview_gcs_path="previews/AAA.webp",
        original_gcs_path="originals/AAA.jpg",
        width=1280,
        height=960,
        latitude=None,
        longitude=None,
    )


def test_exists_returns_false_when_doc_not_found(repo, mock_db):
    mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
    assert repo.exists("UNKNOWN_ID") is False


def test_exists_returns_true_when_doc_found(repo, mock_db):
    mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = [MagicMock()]
    assert repo.exists("AAA") is True


def test_exists_queries_by_google_photos_id(repo, mock_db):
    mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
    repo.exists("TARGET_ID")
    mock_db.collection.return_value.where.assert_called_once_with(
        "google_photos_id", "==", "TARGET_ID"
    )


def test_upsert_writes_to_firestore(repo, mock_db):
    doc = _doc()
    repo.upsert(doc)
    mock_db.collection.return_value.document.return_value.set.assert_called_once()


def test_upsert_uses_google_photos_id_as_document_id(repo, mock_db):
    doc = _doc(google_photos_id="UNIQUE_XYZ")
    repo.upsert(doc)
    mock_db.collection.return_value.document.assert_called_once_with("UNIQUE_XYZ")


def test_upsert_includes_all_required_fields(repo, mock_db):
    doc = _doc()
    repo.upsert(doc)
    written = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    for field in ("google_photos_id", "filename", "taken_at", "preview_gcs_path", "original_gcs_path", "width", "height"):
        assert field in written, f"Missing field: {field}"
