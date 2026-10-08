"""
A photo or video from the Photo Index, as the Compilation Job sees it.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class MediaItem:
    id: str  # google_photos_id
    media_type: str  # "photo" or "video"
    filename: str
    taken_at: datetime  # UTC, from the Sidecar
    latitude: Optional[float]
    longitude: Optional[float]
    original_path: Optional[str] = None
    preview_path: Optional[str] = None
    # Set by trips.localise: where and in which time zone it was taken.
    time_zone: str = "UTC"
    local: Optional[datetime] = None
    place: Optional[str] = None
    # Set by trips.find_trips: taken near home (departure and return days are part of a trip).
    near_home: bool = False

    @property
    def is_video(self) -> bool:
        return self.media_type == "video"

    @property
    def located(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def day(self) -> date:
        """The local date it was taken."""
        return (self.local or self.taken_at).date()
