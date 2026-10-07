"""
In-memory adapters for the Media Indexer's ports. Thread-safe, because media is
indexed on a thread pool.
"""
import threading
from dataclasses import dataclass

from src.photo_index_repository import PhotoDoc


@dataclass
class StoredBlob:
    data: bytes
    content_type: str


class InMemoryBlobStore:
    def __init__(self, fail_with: Exception | None = None):
        self.blobs: dict[str, StoredBlob] = {}
        self._fail_with = fail_with
        self._lock = threading.Lock()

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        with self._lock:
            self.blobs[path] = StoredBlob(data, content_type)


class InMemoryPhotoIndex:
    def __init__(self, docs: list[PhotoDoc] = ()):
        self.docs: dict[str, PhotoDoc] = {doc.google_photos_id: doc for doc in docs}
        self._lock = threading.Lock()

    def exists(self, google_photos_id: str) -> bool:
        with self._lock:
            return google_photos_id in self.docs

    def upsert(self, doc: PhotoDoc) -> None:
        with self._lock:
            self.docs[doc.google_photos_id] = doc
