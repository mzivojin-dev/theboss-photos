"""
Google Cloud adapters: the Photo Index and compilations collections in Firestore, and the GCS
buckets media is read from and Compilations are written to.
"""
import os
from typing import Optional

from google.cloud import firestore, storage
from google.cloud.exceptions import NotFound

from .media_item import MediaItem

PHOTO_INDEX = "photos"
COMPILATIONS = "compilations"
PHOTO_INDEX_FIELDS = ["media_type", "filename", "taken_at", "latitude", "longitude",
                      "original_gcs_path", "preview_gcs_path"]


def load_photo_index(db: firestore.Client) -> list[MediaItem]:
    items = []
    for doc in db.collection(PHOTO_INDEX).select(PHOTO_INDEX_FIELDS).stream():
        data = doc.to_dict()
        items.append(MediaItem(
            id=doc.id,
            media_type=data.get("media_type", "photo"),
            filename=data["filename"],
            taken_at=data["taken_at"],
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            original_path=data.get("original_gcs_path"),
            preview_path=data.get("preview_gcs_path"),
        ))
    return items


class FirestoreCompilationStore:
    def __init__(self, db: firestore.Client):
        self._collection = db.collection(COMPILATIONS)

    def get(self, trip_id: str) -> Optional[dict]:
        snapshot = self._collection.document(trip_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def save(self, trip_id: str, fields: dict) -> None:
        self._collection.document(trip_id).set(fields)


class GcsVideoStore:
    def __init__(self, bucket: storage.Bucket):
        self._bucket = bucket

    def upload_file(self, path: str, local_path: str, content_type: str) -> None:
        self._bucket.blob(path).upload_from_filename(local_path, content_type=content_type)


class GcsMediaSource:
    """Reads the staged copy the Ingestion Job wrote. Media indexed before staging existed has none;
    then a video is read from Originals (an Archive read, which costs retrieval) and a photo from
    its 1280px Preview."""

    def __init__(self, staging: storage.Bucket, originals: storage.Bucket, previews: storage.Bucket):
        self._staging = staging
        self._originals = originals
        self._previews = previews

    def fetch(self, item: MediaItem, directory: str) -> Optional[str]:
        extension = os.path.splitext(item.filename)[1].lower() if item.is_video else ".jpg"
        candidates = [(self._staging, f"{item.id}{extension}")]
        if item.is_video and item.original_path:
            candidates.append((self._originals, item.original_path))
        if not item.is_video and item.preview_path:
            candidates.append((self._previews, item.preview_path))
        for bucket, name in candidates:
            local = os.path.join(directory, f"{item.id}{os.path.splitext(name)[1].lower()}")
            try:
                bucket.blob(name).download_to_filename(local)
            except NotFound:
                if os.path.exists(local):
                    os.remove(local)
                continue
            return local
        return None
