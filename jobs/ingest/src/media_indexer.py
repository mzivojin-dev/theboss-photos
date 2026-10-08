"""
Indexes one media file from a Takeout Archive into Originals, Previews and the Photo Index, and
stages it for the Compilation Job.
"""
import logging
from typing import Optional, Protocol

from .image_processor import process as generate_preview, staged_jpeg
from .index_outcome import IndexResult, Outcome
from .media_types import content_type_for, extension_of
from .photo_index_repository import PhotoDoc
from .sidecar_parser import PhotoMetadata

log = logging.getLogger(__name__)


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


class MediaIndexer:
    def __init__(self, originals: BlobStore, previews: BlobStore, photo_index: PhotoIndex,
                 staging: Optional[BlobStore] = None):
        self._originals = originals
        self._previews = previews
        self._photo_index = photo_index
        self._staging = staging

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
        self._stage(metadata.google_photos_id, filename, raw_bytes, media.is_video)
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

    def _stage(self, google_photos_id: str, filename: str, raw_bytes: bytes, is_video: bool) -> None:
        """Copy the bytes already in memory to Staging, so the Compilation Job reads them from Standard
        storage instead of Archive. Staging is optional: if it fails, the file is still indexed and the
        Compilation Job falls back to its Original or Preview."""
        if self._staging is None:
            return
        path = staged_path(google_photos_id, filename, is_video)
        try:
            if is_video:
                self._staging.upload(path, raw_bytes, content_type=content_type_for(filename))
            else:
                self._staging.upload(path, staged_jpeg(raw_bytes), content_type="image/jpeg")
        except Exception as error:
            log.warning("Failed to stage %s: %s: %s", filename, type(error).__name__, error)


def staged_path(google_photos_id: str, filename: str, is_video: bool) -> str:
    """Where a media file is staged: the video as it is, a photo as a JPEG. The Compilation Job
    looks files up by this name."""
    return f"{google_photos_id}{extension_of(filename)}" if is_video else f"{google_photos_id}.jpg"
