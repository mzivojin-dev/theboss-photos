"""
Groups similar photos in the Photo Index (see similar_photos.py). Run by hand or on a schedule:

    python -m src.group_main

Needs GCP_PROJECT_ID and PREVIEWS_BUCKET (see .env.example). Nothing is deleted.
"""
import logging
import os
import sys
from typing import Optional

from google.cloud import firestore, storage
from google.cloud.exceptions import NotFound

from .gcp import PHOTO_INDEX
from .photo_measures import MEASURE_FIELDS
from .similar_photos import Grouping, IndexedPhoto, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIELDS = ["media_type", "taken_at", "preview_gcs_path", "grouped_under", "group_size", "cover_pinned",
          *MEASURE_FIELDS]
BATCH_SIZE = 400  # Firestore allows 500 writes per batch


class FirestorePhotos:
    def __init__(self, db: firestore.Client):
        self._db = db
        self._collection = db.collection(PHOTO_INDEX)

    def photos(self) -> list[IndexedPhoto]:
        result = []
        for doc in self._collection.select(FIELDS).stream():
            data = doc.to_dict()
            if data.get("media_type", "photo") != "photo":
                continue
            measured = all(data.get(field) is not None for field in MEASURE_FIELDS)
            result.append(IndexedPhoto(
                id=doc.id,
                taken_at=data["taken_at"],
                preview_path=data.get("preview_gcs_path"),
                measures={field: data[field] for field in MEASURE_FIELDS} if measured else None,
                grouping=Grouping(data.get("grouped_under"), data.get("group_size")),
                pinned=bool(data.get("cover_pinned")),
            ))
        return result

    def save_measures(self, photo_id: str, measures: dict) -> None:
        self._collection.document(photo_id).update(measures)

    def save_groupings(self, changes: dict[str, Grouping]) -> None:
        items = list(changes.items())
        for start in range(0, len(items), BATCH_SIZE):
            chunk = items[start:start + BATCH_SIZE]
            try:
                self._commit(chunk)
            except NotFound:
                # A photo in the batch was removed since it was read: write the rest one by one.
                for item in chunk:
                    try:
                        self._commit([item])
                    except NotFound:
                        log.warning("Photo %s no longer exists; skipped", item[0])

    def _commit(self, items: list[tuple[str, Grouping]]) -> None:
        batch = self._db.batch()
        for photo_id, grouping in items:
            batch.update(self._collection.document(photo_id), {
                "grouped_under": grouping.under if grouping.under else firestore.DELETE_FIELD,
                "group_size": grouping.size if grouping.size else firestore.DELETE_FIELD,
            })
        batch.commit()


class GcsPreviews:
    def __init__(self, bucket: storage.Bucket):
        self._bucket = bucket

    def fetch(self, preview_path: str, directory: str) -> Optional[str]:
        local = os.path.join(directory, os.path.basename(preview_path))
        try:
            self._bucket.blob(preview_path).download_to_filename(local)
        except NotFound:
            return None
        return local


def main() -> int:
    missing = [name for name in ("GCP_PROJECT_ID", "PREVIEWS_BUCKET") if not os.environ.get(name)]
    if missing:
        log.error("Set %s (see .env.example)", ", ".join(missing))
        return 2
    project = os.environ["GCP_PROJECT_ID"]
    db = firestore.Client(project=project, database="photo-lib")
    previews = storage.Client(project=project).bucket(os.environ["PREVIEWS_BUCKET"])
    # Unreadable photos are logged and shown on their own. They are not a failure: retrying the
    # whole job would not make a broken preview readable.
    run(FirestorePhotos(db), GcsPreviews(previews))
    return 0


if __name__ == "__main__":
    sys.exit(main())
