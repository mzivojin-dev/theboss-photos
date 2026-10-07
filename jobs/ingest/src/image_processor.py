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


@dataclass
class Preview:
    data: bytes  # WebP
    width: int
    height: int


def process(raw_bytes: bytes) -> Preview:
    # Phones store rotated photos as unrotated pixels plus an EXIF Orientation tag;
    # apply it, since the WebP Preview carries no EXIF.
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw_bytes))).convert("RGB")

    long_side = max(img.width, img.height)
    if long_side > MAX_SIDE:
        scale = MAX_SIDE / long_side
        new_width = round(img.width * scale)
        new_height = round(img.height * scale)
        img = img.resize((new_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    return Preview(data=buf.getvalue(), width=img.width, height=img.height)
