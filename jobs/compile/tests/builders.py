"""
Builders for media items, clips and photos in tests.
"""
from datetime import datetime, timedelta, timezone
from itertools import count

from src.edit_plan import Clip, Photo, Signal
from src.media_item import MediaItem
from src.trips import localise

KITCHENER = (43.45, -80.49)
TORONTO = (43.65, -79.38)  # about 90 km from Kitchener
TIMISOARA = (45.75, 21.23)
CONSTANTA = (44.17, 28.63)

ZONES = {KITCHENER: "America/Toronto", TORONTO: "America/Toronto",
         TIMISOARA: "Europe/Bucharest", CONSTANTA: "Europe/Bucharest"}
NAMES = {KITCHENER: "Kitchener", TORONTO: "Toronto", TIMISOARA: "Timisoara", CONSTANTA: "Constanta"}
_ids = count()


def item(when: str, where: tuple[float, float] | None, video: bool = False) -> MediaItem:
    """`when` is UTC, e.g. "2026-07-03 08:33"."""
    n = next(_ids)
    return MediaItem(
        id=f"ID{n}",
        media_type="video" if video else "photo",
        filename=f"PXL_{n}.{'mp4' if video else 'jpg'}",
        taken_at=datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc),
        latitude=where[0] if where else None,
        longitude=where[1] if where else None,
    )


def localised(items: list[MediaItem]) -> list[MediaItem]:
    localise(items, lambda lat, lng: ZONES[(lat, lng)], lambda points: [NAMES[p] for p in points])
    return items


def days(start: str, n: int, where: tuple[float, float], video: bool = False, hour: int = 15) -> list[MediaItem]:
    """One item a day for n days from `start` (a date), at `hour` UTC."""
    first = datetime.strptime(start, "%Y-%m-%d")
    return [item(f"{(first + timedelta(days=d)):%Y-%m-%d} {hour:02}:00", where, video) for d in range(n)]


def clip(media: MediaItem, duration: float = 30.0, loud_from: int | None = None, loud_for: int = 5,
         portrait: bool = True, hdr: bool = True) -> Clip:
    """A clip that is quiet and still, except loud and moving for `loud_for` s from `loud_from`."""
    signals = {}
    for second in range(int(duration)):
        loud = loud_from is not None and loud_from <= second < loud_from + loud_for
        signals[second] = Signal(brightness=0.5, motion=6.0 if loud else 0.5, loudness=-20.0 if loud else -55.0)
    return Clip(item=media, path=f"/tmp/{media.id}.mp4", duration=duration, has_audio=True, hdr=hdr,
                portrait=portrait, signals=signals)


def photo(media: MediaItem, face_score: float = 0.0) -> Photo:
    return Photo(item=media, path=f"/tmp/{media.id}.jpg", faces=1 if face_score else 0, face_score=face_score)
