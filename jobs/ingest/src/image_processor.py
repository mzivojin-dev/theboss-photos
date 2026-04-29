import io
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

MAX_SIDE = 1280
WEBP_QUALITY = 85


def process(raw_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

    long_side = max(img.width, img.height)
    if long_side > MAX_SIDE:
        scale = MAX_SIDE / long_side
        new_width = round(img.width * scale)
        new_height = round(img.height * scale)
        img = img.resize((new_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    return buf.getvalue()
