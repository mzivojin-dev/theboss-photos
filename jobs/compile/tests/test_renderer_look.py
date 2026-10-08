"""
Tests for renderer.Look: the output format follows most of the footage.
"""
from src.renderer import Look
from tests.builders import clip, item


def _clip(seconds: float, portrait: bool, hdr: bool):
    return clip(item("2026-07-03 08:00", None, video=True), duration=seconds, portrait=portrait, hdr=hdr)


def test_mostly_portrait_hdr_footage_makes_a_portrait_hdr_compilation():
    look = Look.for_clips([_clip(60, portrait=True, hdr=True), _clip(30, portrait=False, hdr=False)])

    assert (look.width, look.height, look.hdr) == (1080, 1920, True)
    assert "libx265" in look.encode and "arib-std-b67" in look.encode


def test_mostly_landscape_sdr_footage_makes_a_landscape_h264_compilation():
    look = Look.for_clips([_clip(20, portrait=True, hdr=True), _clip(40, portrait=False, hdr=False)])

    assert (look.width, look.height, look.hdr) == (1920, 1080, False)
    assert "libx264" in look.encode
