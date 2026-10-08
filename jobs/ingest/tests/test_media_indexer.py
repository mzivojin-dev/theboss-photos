"""
Tests for media_indexer.MediaIndexer: indexing one media file into Originals,
Previews and the Photo Index.
"""
import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from src.index_outcome import Outcome
from src.media_indexer import MediaIndexer
from src.photo_index_repository import PhotoDoc
from src.sidecar_parser import PhotoMetadata
from tests.in_memory_adapters import InMemoryBlobStore, InMemoryPhotoIndex, StoredBlob

TAKEN_AT = datetime(2026, 6, 12, tzinfo=timezone.utc)


class FakeMediaFile:
    def __init__(self, name: str, data: bytes = b"bytes", is_video: bool = False):
        self.name = name
        self.is_video = is_video
        self._data = data
        self.reads = 0

    def read(self) -> bytes:
        self.reads += 1
        return self._data


def _image(width: int, height: int, format: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(100, 149, 237)).save(buf, format=format)
    return buf.getvalue()


def _indexer(originals=None, previews=None, photo_index=None) -> MediaIndexer:
    return MediaIndexer(
        originals=originals if originals is not None else InMemoryBlobStore(),
        previews=previews if previews is not None else InMemoryBlobStore(),
        photo_index=photo_index if photo_index is not None else InMemoryPhotoIndex(),
    )


def _metadata(google_photos_id: str = "AAA") -> PhotoMetadata:
    return PhotoMetadata(google_photos_id=google_photos_id, taken_at=TAKEN_AT, latitude=None, longitude=None)


def test_already_indexed_media_is_neither_read_nor_written():
    existing = PhotoDoc(google_photos_id="AAA", filename="IMG_1.jpg", taken_at=TAKEN_AT, latitude=None, longitude=None)
    originals, previews = InMemoryBlobStore(), InMemoryBlobStore()
    indexer = MediaIndexer(originals=originals, previews=previews, photo_index=InMemoryPhotoIndex([existing]))
    media = FakeMediaFile("Takeout/Google Photos/IMG_1.jpg")

    result = indexer.index(media, _metadata("AAA"))

    assert result.outcome is Outcome.ALREADY_INDEXED
    assert media.reads == 0
    assert originals.blobs == {} and previews.blobs == {}


def test_photo_is_stored_as_original_and_preview_and_indexed_with_its_dimensions():
    originals, previews, photo_index = InMemoryBlobStore(), InMemoryBlobStore(), InMemoryPhotoIndex()
    photo = _image(3000, 2000)

    result = _indexer(originals, previews, photo_index).index(
        FakeMediaFile("Takeout/Google Photos/IMG_1.jpg", photo), _metadata("AAA")
    )

    assert result.outcome is Outcome.INDEXED
    assert originals.blobs["AAA_IMG_1.jpg"].data == photo
    assert previews.blobs["AAA.webp"].content_type == "image/webp"
    assert photo_index.docs["AAA"] == PhotoDoc(
        google_photos_id="AAA",
        filename="IMG_1.jpg",
        taken_at=TAKEN_AT,
        latitude=None,
        longitude=None,
        media_type="photo",
        original_gcs_path="AAA_IMG_1.jpg",
        preview_gcs_path="AAA.webp",
        width=1280,
        height=853,
    )


def test_video_is_stored_as_original_only():
    originals, previews, photo_index = InMemoryBlobStore(), InMemoryBlobStore(), InMemoryPhotoIndex()

    result = _indexer(originals, previews, photo_index).index(
        FakeMediaFile("Takeout/Google Photos/PXL_1.mp4", b"video", is_video=True), _metadata("VID")
    )

    assert result.outcome is Outcome.INDEXED
    assert originals.blobs["VID_PXL_1.mp4"].data == b"video"
    assert previews.blobs == {}
    assert photo_index.docs["VID"] == PhotoDoc(
        google_photos_id="VID",
        filename="PXL_1.mp4",
        taken_at=TAKEN_AT,
        latitude=None,
        longitude=None,
        media_type="video",
        original_gcs_path="VID_PXL_1.mp4",
    )


@pytest.mark.parametrize("filename, image_format, content_type", [
    ("IMG_1.JPG", "JPEG", "image/jpeg"),
    ("IMG_1.png", "PNG", "image/png"),
    ("IMG_1.gif", "GIF", "image/gif"),
    ("IMG_1.webp", "WEBP", "image/webp"),
    ("IMG_1.tif", "TIFF", "image/tiff"),
    ("IMG_1.bmp", "BMP", "image/bmp"),
])
def test_photo_original_is_stored_with_the_content_type_of_its_extension(filename, image_format, content_type):
    originals = InMemoryBlobStore()

    _indexer(originals=originals).index(FakeMediaFile(filename, _image(10, 10, image_format)), _metadata("AAA"))

    assert originals.blobs[f"AAA_{filename}"].content_type == content_type


@pytest.mark.parametrize("filename, content_type", [
    ("PXL_1.mp4", "video/mp4"),
    ("PXL_1.MOV", "video/quicktime"),
    ("PXL_1.m4v", "video/x-m4v"),
    ("PXL_1.3gp", "video/3gpp"),
    ("PXL_1.avi", "video/x-msvideo"),
    ("PXL_1.mkv", "video/x-matroska"),
    ("PXL_1.wmv", "video/x-ms-wmv"),
    ("PXL_1.unknownext", "application/octet-stream"),
])
def test_video_original_is_stored_with_the_content_type_of_its_extension(filename, content_type):
    originals = InMemoryBlobStore()

    _indexer(originals=originals).index(FakeMediaFile(filename, b"video", is_video=True), _metadata("VID"))

    assert originals.blobs[f"VID_{filename}"].content_type == content_type


def test_corrupt_image_fails_without_being_indexed():
    photo_index = InMemoryPhotoIndex()

    result = _indexer(photo_index=photo_index).index(FakeMediaFile("IMG_1.jpg", b"not an image"), _metadata("AAA"))

    assert result.outcome is Outcome.FAILED
    assert result.reason
    assert photo_index.docs == {}


@pytest.mark.parametrize("failing_store", ["originals", "previews"])
def test_a_failed_upload_leaves_no_photo_index_document(failing_store):
    stores = {"originals": InMemoryBlobStore(), "previews": InMemoryBlobStore()}
    stores[failing_store] = InMemoryBlobStore(fail_with=OSError("bucket not found"))
    photo_index = InMemoryPhotoIndex()

    result = _indexer(**stores, photo_index=photo_index).index(FakeMediaFile("IMG_1.jpg", _image(10, 10)), _metadata("AAA"))

    assert result.outcome is Outcome.FAILED
    assert "bucket not found" in result.reason
    assert photo_index.docs == {}


def test_a_staged_video_is_its_bytes_unchanged():
    staging = InMemoryBlobStore()
    indexer = MediaIndexer(InMemoryBlobStore(), InMemoryBlobStore(), InMemoryPhotoIndex(), staging=staging)

    indexer.index(FakeMediaFile("Takeout/Google Photos/VID_1.MP4", b"video", is_video=True), _metadata("VVV"))

    assert staging.blobs["VVV.mp4"] == StoredBlob(b"video", "video/mp4")


def test_a_staged_photo_is_an_upright_jpeg_at_most_1920_pixels():
    staging = InMemoryBlobStore()
    indexer = MediaIndexer(InMemoryBlobStore(), InMemoryBlobStore(), InMemoryPhotoIndex(), staging=staging)
    rotated = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise to display
    Image.new("RGB", (4000, 3000)).save(rotated, format="JPEG", exif=exif)

    indexer.index(FakeMediaFile("Takeout/Google Photos/IMG_1.HEIC", rotated.getvalue()), _metadata("AAA"))

    staged = staging.blobs["AAA.jpg"]
    assert staged.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(staged.data)).size == (1440, 1920)


def test_nothing_is_staged_when_media_is_already_indexed():
    existing = PhotoDoc(google_photos_id="AAA", filename="IMG_1.jpg", taken_at=TAKEN_AT, latitude=None, longitude=None)
    staging = InMemoryBlobStore()
    indexer = MediaIndexer(InMemoryBlobStore(), InMemoryBlobStore(), InMemoryPhotoIndex([existing]), staging=staging)

    indexer.index(FakeMediaFile("Takeout/Google Photos/IMG_1.jpg", _image(10, 10)), _metadata("AAA"))

    assert staging.blobs == {}


def test_a_failed_staging_upload_leaves_no_photo_index_document():
    photo_index = InMemoryPhotoIndex()
    indexer = MediaIndexer(InMemoryBlobStore(), InMemoryBlobStore(), photo_index,
                           staging=InMemoryBlobStore(fail_with=OSError("staging down")))

    result = indexer.index(FakeMediaFile("Takeout/Google Photos/IMG_1.jpg", _image(10, 10)), _metadata("AAA"))

    assert result.outcome is Outcome.FAILED
    assert photo_index.docs == {}
