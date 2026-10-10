"""
In-memory adapters for the Media Indexer's ports. Thread-safe, because media is
indexed on a thread pool.
"""
import threading
from dataclasses import dataclass

from src.ingestion_ledger import Problem
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


class InMemoryIngestionLedger:
    """problems: (export, path) -> Problem; resolved: the keys that have been resolved;
    exports: export -> {"exported_at", "archives", "years"}."""

    def __init__(self):
        self.problems: dict[tuple[str, str], Problem] = {}
        self.resolved: set[tuple[str, str]] = set()
        self.exports: dict[str, dict] = {}

    def unresolved(self) -> set[tuple[str, str]]:
        return set(self.problems) - self.resolved

    def record_problem(self, problem: Problem) -> None:
        key = (problem.export, problem.path)
        self.problems[key] = problem
        self.resolved.discard(key)

    def resolve(self, export: str, path: str) -> None:
        self.resolved.add((export, path))

    def record_export(self, export, exported_at, archives, years) -> None:
        merged = self.exports.setdefault(export, {"exported_at": exported_at, "archives": set(), "years": set()})
        merged["archives"] |= set(archives)
        merged["years"] |= set(years)
