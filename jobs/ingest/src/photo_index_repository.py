from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PhotoDoc:
    google_photos_id: str
    filename: str
    taken_at: datetime
    preview_gcs_path: str
    original_gcs_path: str
    width: int
    height: int
    latitude: Optional[float]
    longitude: Optional[float]


class PhotoIndexRepository:
    COLLECTION = "photos"

    def __init__(self, db):
        self._db = db

    def exists(self, google_photos_id: str) -> bool:
        results = (
            self._db.collection(self.COLLECTION)
            .where("google_photos_id", "==", google_photos_id)
            .limit(1)
            .get()
        )
        return len(results) > 0

    def upsert(self, doc: PhotoDoc) -> None:
        data = {
            "google_photos_id": doc.google_photos_id,
            "filename": doc.filename,
            "taken_at": doc.taken_at,
            "preview_gcs_path": doc.preview_gcs_path,
            "original_gcs_path": doc.original_gcs_path,
            "width": doc.width,
            "height": doc.height,
            "latitude": doc.latitude,
            "longitude": doc.longitude,
        }
        self._db.collection(self.COLLECTION).document(doc.google_photos_id).set(data)
