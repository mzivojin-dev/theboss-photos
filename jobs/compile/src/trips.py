"""
Finds Trips in the Photo Index: runs of days away from home that have video.

Sidecar times are UTC, so every item is first put in the local time where it was taken: a Saturday
evening in Ontario must not count as Sunday.
"""
import bisect
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .media_item import MediaItem

# A day is away from home if anything that day was taken farther than this from it.
AWAY_KM = 50.0

TimeZoneAt = Callable[[float, float], Optional[str]]
PlaceNames = Callable[[list[tuple[float, float]]], list[str]]


@dataclass(frozen=True)
class Trip:
    items: tuple[MediaItem, ...]  # in time order

    @property
    def first_day(self) -> date:
        return self.items[0].day

    @property
    def last_day(self) -> date:
        return self.items[-1].day

    @property
    def id(self) -> str:
        return f"{self.first_day}_{self.last_day}"

    @property
    def clips(self) -> list[MediaItem]:
        return [i for i in self.items if i.is_video]

    @property
    def photos(self) -> list[MediaItem]:
        return [i for i in self.items if not i.is_video]

    @property
    def membership(self) -> str:
        """Changes whenever an item joins or leaves the trip, so its Compilation is made again."""
        return hashlib.sha256("\n".join(sorted(i.id for i in self.items)).encode()).hexdigest()


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def localise(items: list[MediaItem], time_zone_at: TimeZoneAt, place_names: PlaceNames) -> None:
    """Set each item's local time and place. Items without GPS take the time zone of the item
    nearest in time that has one."""
    located = [i for i in items if i.located]
    for item in located:
        item.time_zone = time_zone_at(item.latitude, item.longitude) or "UTC"
    if located:
        for item, place in zip(located, place_names([(i.latitude, i.longitude) for i in located])):
            item.place = place
    by_time = sorted(located, key=lambda i: i.taken_at)
    times = [i.taken_at for i in by_time]
    for item in items:
        if not item.located:
            nearest = _nearest_in_time(by_time, times, item.taken_at)
            item.time_zone = nearest.time_zone if nearest else "UTC"
        item.local = item.taken_at.astimezone(ZoneInfo(item.time_zone))


def _nearest_in_time(by_time: list[MediaItem], times: list, moment) -> Optional[MediaItem]:
    k = bisect.bisect_left(times, moment)
    neighbours = by_time[max(0, k - 1):k + 1]
    return min(neighbours, key=lambda i: abs(i.taken_at - moment), default=None)


def find_home(items: list[MediaItem], away_km: float = AWAY_KM) -> Optional[tuple[float, float]]:
    """The place with the most *days* of media within away_km. Not the most media: a busy holiday
    can produce more photos than months at home."""
    # Media is grouped into cells of 0.1 degree (about 10 km) first, so this is cells x cells, not
    # cells x media: a library of 100k items has a few thousand cells at most.
    days_by_cell: dict[tuple[float, float], set[date]] = defaultdict(set)
    for i in items:
        if i.located:
            days_by_cell[(round(i.latitude, 1), round(i.longitude, 1))].add(i.day)
    cells = list(days_by_cell)

    def days_near(cell: tuple[float, float]) -> int:
        return len(set().union(*(days_by_cell[other] for other in cells if km(cell, other) <= away_km)))

    return max(cells, key=days_near, default=None)


def find_trips(items: list[MediaItem], away_km: float = AWAY_KM) -> list[Trip]:
    """Trips with at least one video, in time order. Items must be localised.

    A trip is a run of away days that ends only at a day with media at home, so days without
    photos in the middle of a trip don't split it."""
    home = find_home(items, away_km)
    if home is None:
        return []
    located = [i for i in items if i.located]
    for i in located:
        i.near_home = km(home, (i.latitude, i.longitude)) <= away_km
    away = {i.day for i in located if not i.near_home}
    home_days = {i.day for i in located} - away

    runs: list[list[date]] = []
    for day in sorted(away | home_days):
        if day in home_days:
            runs.append([])
        elif runs and runs[-1]:
            runs[-1].append(day)
        else:
            runs.append([day])
    ordered = sorted(items, key=lambda i: i.taken_at)
    trips = [Trip(tuple(i for i in ordered if run[0] <= i.day <= run[-1])) for run in runs if run]
    return [trip for trip in trips if trip.clips]
