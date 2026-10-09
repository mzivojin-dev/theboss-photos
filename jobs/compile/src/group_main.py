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
from .similar_photos import IndexedPhoto, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIELDS = ["media_type", "taken_at", "preview_gcs_path", "grouped_under", "group_size",
          "similar_hash", "similar_faces", "similar_face_score", "similar_sharpness", "similar_exposure"]
MEASURE_FIELDS = FIELDS[5:]


class FirestorePhotos:
    def __init__(self, db: firestore.Client):
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
                grouped_under=data.get("grouped_under"),
                group_size=data.get("group_size"),
            ))
        return result

    def save_measures(self, photo_id: str, measures: dict) -> None:
        self._collection.document(photo_id).update(measures)

    def save_group(self, photo_id: str, grouped_under: Optional[str], group_size: Optional[int]) -> None:
        self._collection.document(photo_id).update({
            "grouped_under": grouped_under if grouped_under else firestore.DELETE_FIELD,
            "group_size": group_size if group_size else firestore.DELETE_FIELD,
        })


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
    summary = run(FirestorePhotos(db), GcsPreviews(previews))
    return 1 if summary.unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
