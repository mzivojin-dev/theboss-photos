"""
Tests for FirestoreIngestionLedger against a mocked Firestore client. The in-memory ledger used by the
ingestion tests accepts anything, so the Firestore rules (such as ArrayUnion rejecting an empty list)
are checked here, with the real ArrayUnion.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from google.cloud.firestore import ArrayUnion

from src.ingestion_ledger import FirestoreIngestionLedger

EXPORTED_AT = datetime(2026, 10, 5, 23, 27, 35, tzinfo=timezone.utc)


def _record(archives, years):
    db = MagicMock()
    FirestoreIngestionLedger(db).record_export("20261005T232735Z", EXPORTED_AT, archives, years)
    exports = db.collection.return_value
    exports.document.assert_called_once_with("20261005T232735Z")
    (data,), kwargs = exports.document.return_value.set.call_args
    assert kwargs == {"merge": True}
    return data


def test_an_export_is_merged_with_its_archives_and_years():
    data = _record({"takeout-b.zip", "takeout-a.zip"}, {2026, 2024})

    assert data["exported_at"] == EXPORTED_AT
    assert isinstance(data["archives"], ArrayUnion) and data["archives"].values == ["takeout-a.zip", "takeout-b.zip"]
    assert isinstance(data["years"], ArrayUnion) and data["years"].values == [2024, 2026]


def test_an_archive_without_a_photos_year_folder_still_records_the_export():
    data = _record({"takeout-a.zip"}, set())

    assert "years" not in data
    assert data["archives"].values == ["takeout-a.zip"]
    assert data["exported_at"] == EXPORTED_AT
