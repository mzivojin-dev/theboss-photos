"""
Indexes one media file from a Takeout Archive into Originals, Previews and the Photo Index.
"""
import enum
import logging
import mimetypes
from dataclasses import dataclass
from typing import Optional, Protocol

from .image_processor import process as generate_preview
from .photo_index_repository import PhotoDoc
from .sidecar_parser import PhotoMetadata

log = logging.getLogger(__name__)

# The extensions the Ingestion Job accepts. mimetypes alone is platform-dependent
# (it reads the OS registry on Windows) and lacks some of these.
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".3gp": "video/3gpp",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".wmv": "video/x-ms-wmv",
}


def content_type_for(filename: str) -> str:
    extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    return (
        CONTENT_TYPES.get(extension)
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )


class MediaFile(Protocol):
    """A media file whose bytes are read lazily, only once they are needed."""
    name: str
    is_video: bool

    def read(self) -> bytes: ...


class BlobStore(Protocol):
    def upload(self, path: str, data: bytes, content_type: str) -> None: ...


class PhotoIndex(Protocol):
    def exists(self, google_photos_id: str) -> bool: ...

    def upsert(self, doc: PhotoDoc) -> None: ...


class Outcome(enum.Enum):
    INDEXED = "indexed"
    ALREADY_INDEXED = "already indexed"
    FAILED = "failed"


@dataclass(frozen=True)
class IndexResult:
    outcome: Outcome
    reason: Optional[str] = None


class MediaIndexer:
    def __init__(self, originals: BlobStore, previews: BlobStore, photo_index: PhotoIndex):
        self._originals = originals
        self._previews = previews
        self._photo_index = photo_index

    def index(self, media: MediaFile, metadata: PhotoMetadata) -> IndexResult:
        """Index one media file. Never raises: a failure is returned as FAILED, so it can't stop the run."""
        try:
            result = self._index(media, metadata)
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            log.warning("Failed to index %s: %s", media.name, reason)
            return IndexResult(Outcome.FAILED, reason)
        if result.outcome is Outcome.INDEXED:
            log.info("Indexed: %s", media.name)
        return result

    def _index(self, media: MediaFile, metadata: PhotoMetadata) -> IndexResult:
        if self._photo_index.exists(metadata.google_photos_id):
            return IndexResult(Outcome.ALREADY_INDEXED)

        raw_bytes = media.read()
        filename = media.name.split("/")[-1]
        original_path = f"{metadata.google_photos_id}_{filename}"

        # The Photo Index document is written last: its presence means the file is fully indexed.
        self._originals.upload(original_path, raw_bytes, content_type=content_type_for(filename))
        if media.is_video:
            self._photo_index.upsert(PhotoDoc(
                google_photos_id=metadata.google_photos_id,
                filename=filename,
                taken_at=metadata.taken_at,
                latitude=metadata.latitude,
                longitude=metadata.longitude,
                media_type="video",
                original_gcs_path=original_path,
            ))
            return IndexResult(Outcome.INDEXED)

        preview = generate_preview(raw_bytes)
        preview_path = f"{metadata.google_photos_id}.webp"
        self._previews.upload(preview_path, preview.data, content_type="image/webp")
        self._photo_index.upsert(PhotoDoc(
            google_photos_id=metadata.google_photos_id,
            filename=filename,
            taken_at=metadata.taken_at,
            latitude=metadata.latitude,
            longitude=metadata.longitude,
            media_type="photo",
            original_gcs_path=original_path,
            preview_gcs_path=preview_path,
            width=preview.width,
            height=preview.height,
        ))
        return IndexResult(Outcome.INDEXED)
