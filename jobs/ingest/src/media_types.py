"""
The file extensions the Ingestion Job accepts, and the content types of media.
"""
import posixpath

# Not mimetypes: it is platform-dependent (it reads the OS registry on Windows) and lacks some of these.
IMAGE_CONTENT_TYPES = {
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
}
VIDEO_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".3gp": "video/3gpp",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".wmv": "video/x-ms-wmv",
}

IMAGE_EXTENSIONS = frozenset(IMAGE_CONTENT_TYPES)
VIDEO_EXTENSIONS = frozenset(VIDEO_CONTENT_TYPES)
SIDECAR_EXTENSIONS = frozenset({".json"})


def extension_of(filename: str) -> str:
    """The lowercased extension, with its dot, or "" if there is none."""
    return posixpath.splitext(posixpath.basename(filename))[1].lower()


def content_type_for(filename: str) -> str:
    extension = extension_of(filename)
    return (
        IMAGE_CONTENT_TYPES.get(extension)
        or VIDEO_CONTENT_TYPES.get(extension)
        or "application/octet-stream"
    )
