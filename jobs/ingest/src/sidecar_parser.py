import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PhotoMetadata:
    google_photos_id: str
    taken_at: datetime
    latitude: Optional[float]
    longitude: Optional[float]


def parse(json_bytes: bytes) -> PhotoMetadata:
    data = json.loads(json_bytes)

    if "url" not in data:
        raise ValueError("Sidecar missing required field: url")
    if "photoTakenTime" not in data:
        raise ValueError("Sidecar missing required field: photoTakenTime")

    url: str = data["url"]
    google_photos_id = url.rstrip("/").split("/")[-1]

    timestamp = int(data["photoTakenTime"]["timestamp"])
    taken_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    latitude = None
    longitude = None
    geo = data.get("geoDataExif") or data.get("geoData")
    if geo:
        lat = geo.get("latitude", 0.0)
        lng = geo.get("longitude", 0.0)
        if lat != 0.0 or lng != 0.0:
            latitude = lat
            longitude = lng

    return PhotoMetadata(
        google_photos_id=google_photos_id,
        taken_at=taken_at,
        latitude=latitude,
        longitude=longitude,
    )
