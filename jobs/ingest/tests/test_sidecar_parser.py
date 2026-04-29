"""
RED: tests for sidecar_parser.parse()

All tests fail until src/sidecar_parser.py is implemented.
"""
import json
import pytest
from src.sidecar_parser import parse, PhotoMetadata


def _sidecar(**kwargs) -> bytes:
    base = {
        "title": "IMG_0001.jpg",
        "description": "",
        "imageViews": "0",
        "creationTime": {"timestamp": "1609459200", "formatted": "Jan 1, 2021, 12:00:00 AM UTC"},
        "photoTakenTime": {"timestamp": "1609459200", "formatted": "Jan 1, 2021, 12:00:00 AM UTC"},
        "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
        "geoDataExif": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
        "url": "https://photos.google.com/photo/ABC123XYZ",
        "googlePhotosOrigin": {},
    }
    base.update(kwargs)
    return json.dumps(base).encode()


def test_parse_returns_photo_metadata():
    result = parse(_sidecar())
    assert isinstance(result, PhotoMetadata)


def test_parse_extracts_google_photos_id():
    data = _sidecar(url="https://photos.google.com/photo/UNIQUE_ID_001")
    result = parse(data)
    assert result.google_photos_id == "UNIQUE_ID_001"


def test_parse_extracts_taken_at_as_datetime():
    from datetime import datetime, timezone
    data = _sidecar()
    result = parse(data)
    assert result.taken_at == datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_parse_extracts_gps_when_nonzero():
    data = _sidecar(geoDataExif={"latitude": 48.8566, "longitude": 2.3522, "altitude": 35.0})
    result = parse(data)
    assert result.latitude == pytest.approx(48.8566)
    assert result.longitude == pytest.approx(2.3522)


def test_parse_returns_none_gps_when_zero_coordinates():
    data = _sidecar(geoDataExif={"latitude": 0.0, "longitude": 0.0, "altitude": 0.0})
    result = parse(data)
    assert result.latitude is None
    assert result.longitude is None


def test_parse_handles_missing_geo_field():
    base = json.loads(_sidecar())
    del base["geoDataExif"]
    result = parse(json.dumps(base).encode())
    assert result.latitude is None
    assert result.longitude is None


def test_parse_raises_on_missing_url():
    base = json.loads(_sidecar())
    del base["url"]
    with pytest.raises(ValueError, match="url"):
        parse(json.dumps(base).encode())


def test_parse_raises_on_missing_photo_taken_time():
    base = json.loads(_sidecar())
    del base["photoTakenTime"]
    with pytest.raises(ValueError, match="photoTakenTime"):
        parse(json.dumps(base).encode())
