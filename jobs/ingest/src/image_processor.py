import io
from dataclasses import dataclass

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

MAX_SIDE = 1280
WEBP_QUALITY = 85
# Staged photos are larger than Previews: a Compilation fills a 1080x1920 frame with them.
STAGED_MAX_SIDE = 1920
STAGED_JPEG_QUALITY = 90


@dataclass
class Preview:
    data: bytes  # WebP
    width: int
    height: int


def process(raw_bytes: bytes) -> Preview:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

    long_side = max(img.width, img.height)
    if long_side > MAX_SIDE:
        scale = MAX_SIDE / long_side
        new_width = round(img.width * scale)
        new_height = round(img.height * scale)
        img = img.resize((new_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    return Preview(data=buf.getvalue(), width=img.width, height=img.height)


def staged_jpeg(raw_bytes: bytes) -> bytes:
    """An upright JPEG of a photo, at most STAGED_MAX_SIDE on its long side, for the Compilation Job."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw_bytes))).convert("RGB")
    img.thumbnail((STAGED_MAX_SIDE, STAGED_MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=STAGED_JPEG_QUALITY)
    return buf.getvalue()
