"""
RED: tests for image_processor.process()

All tests fail until src/image_processor.py is implemented.
"""
import io
import pytest
from PIL import Image
from src.image_processor import process


def _make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_png(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(255, 99, 71))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_process_returns_bytes():
    result = process(_make_jpeg(2000, 1500))
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_output_is_valid_webp():
    result = process(_make_jpeg(2000, 1500))
    img = Image.open(io.BytesIO(result))
    assert img.format == "WEBP"


def test_wide_image_resized_to_1280_width():
    result = process(_make_jpeg(3000, 2000))
    img = Image.open(io.BytesIO(result))
    assert img.width == 1280


def test_wide_image_aspect_ratio_preserved():
    result = process(_make_jpeg(3000, 2000))
    img = Image.open(io.BytesIO(result))
    expected_height = round(2000 * (1280 / 3000))
    assert abs(img.height - expected_height) <= 1


def test_tall_image_resized_by_height_to_1280():
    # Portrait: height > width — 1280 applies to the long side
    result = process(_make_jpeg(1000, 3000))
    img = Image.open(io.BytesIO(result))
    assert img.height == 1280


def test_tall_image_aspect_ratio_preserved():
    result = process(_make_jpeg(1000, 3000))
    img = Image.open(io.BytesIO(result))
    expected_width = round(1000 * (1280 / 3000))
    assert abs(img.width - expected_width) <= 1


def test_small_image_not_upscaled():
    # Images already smaller than 1280 should not be enlarged
    result = process(_make_jpeg(800, 600))
    img = Image.open(io.BytesIO(result))
    assert img.width == 800
    assert img.height == 600


def test_accepts_png_input():
    result = process(_make_png(2000, 1500))
    img = Image.open(io.BytesIO(result))
    assert img.format == "WEBP"


def test_output_size_under_300kb_for_typical_photo():
    result = process(_make_jpeg(4000, 3000))
    assert len(result) < 300 * 1024
