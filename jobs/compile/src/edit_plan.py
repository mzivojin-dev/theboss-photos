"""
Plans a Compilation from a trip's clips and photos with plain rules, no AI:

- The video is about a third of the footage, between 45 s and 10 minutes.
- Each clip keeps its best stretch: loud (people talking, laughing), some movement, not dark,
  not a whip pan.
- Photos fill the gaps: the best of each burst, none a clip already covers, spread over the trip,
  preferring clear faces.
- One chapter per local day, its title over the first shot. Captions give place and time of day,
  only when they change.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from .media_item import MediaItem
from .trips import Trip

SHARE_OF_FOOTAGE, MIN_SECONDS, MAX_SECONDS = 0.35, 45.0, 600.0
# How much of one clip to keep, before scaling toward the target length.
MIN_CUT, MAX_CUT = 3.0, 12.0
PHOTO_SECONDS = 3.0
# Photos this close together are one burst, and a clip covers the moments this close to it.
BURST = timedelta(seconds=20)
# A trip gets a Compilation only with at least this many clips or this much footage.
MIN_TRIP_CLIPS, MIN_TRIP_FOOTAGE = 3, 60.0


@dataclass(frozen=True)
class Signal:
    """One second of a clip, as measured from its picture and sound."""
    brightness: float  # 0-1
    motion: float  # mean frame difference, 8-bit scale
    loudness: float  # dB RMS


QUIET = Signal(brightness=0.5, motion=0.0, loudness=-60.0)


@dataclass
class Clip:
    item: MediaItem
    path: str
    duration: float
    has_audio: bool
    hdr: bool
    portrait: bool
    signals: dict[int, Signal]


@dataclass
class Photo:
    item: MediaItem
    path: str
    faces: int
    face_score: float  # 0-1, grows with the size of clear faces


@dataclass
class Segment:
    source: Clip | Photo
    start: float
    length: float
    caption: str = ""
    chapter_title: str = ""  # shown over the first shot of a chapter

    @property
    def is_clip(self) -> bool:
        return isinstance(self.source, Clip)


@dataclass
class Chapter:
    title: str
    segments: list[Segment] = field(default_factory=list)


@dataclass
class EditPlan:
    title: str
    dates: str
    chapters: list[Chapter]


def footage_seconds(clips: list[Clip]) -> float:
    return sum(c.duration for c in clips)


def enough_footage(clips: list[Clip]) -> bool:
    return len(clips) >= MIN_TRIP_CLIPS or footage_seconds(clips) >= MIN_TRIP_FOOTAGE


def second_score(s: Signal) -> float:
    loud = min(1.0, max(0.0, (s.loudness + 50) / 35))  # -50 dB silent .. -15 dB talking or laughing
    motion = min(s.motion, 8) / 8 - (0.6 if s.motion > 18 else 0)  # some movement good, whip pans bad
    dark = 0.6 if s.brightness < 0.12 else 0
    return 0.5 * loud + 0.35 * motion - dark


def best_window(clip: Clip, length: float) -> tuple[float, float]:
    """The start of the clip's best `length` seconds, and their mean score."""
    scores = [second_score(clip.signals.get(s, QUIET)) for s in range(int(clip.duration))]
    if not scores:
        return 0.0, 0.0
    span = max(1, min(len(scores), round(length)))
    best = max(range(len(scores) - span + 1), key=lambda s: sum(scores[s:s + span]))
    return float(best), sum(scores[best:best + span]) / span


def pick_photos(photos: list[Photo], clips: list[Clip], budget: int) -> list[Photo]:
    """The best photo of each burst, skipping moments a clip covers, then the best photo of each of
    `budget` equal slices of the trip, so photos stay spread over it."""
    bursts: list[list[Photo]] = []
    for photo in sorted(photos, key=lambda p: p.item.taken_at):
        if any(abs(photo.item.taken_at - c.item.taken_at) < BURST for c in clips):
            continue
        if bursts and photo.item.taken_at - bursts[-1][-1].item.taken_at < BURST:
            bursts[-1].append(photo)
        else:
            bursts.append([photo])
    kept = [max(burst, key=lambda p: p.face_score) for burst in bursts]
    if len(kept) <= budget:
        return kept
    step = len(kept) / budget
    return [max(kept[int(n * step):int((n + 1) * step)], key=lambda p: p.face_score) for n in range(budget)]


def time_of_day(moment: datetime) -> str:
    if moment.hour < 12:
        return "morning"
    if moment.hour < 17:
        return "afternoon"
    return "evening" if moment.hour < 22 else "night"


def plan_edit(trip: Trip, clips: list[Clip], photos: list[Photo]) -> EditPlan:
    target = max(MIN_SECONDS, min(MAX_SECONDS, footage_seconds(clips) * SHARE_OF_FOOTAGE))
    picked = pick_photos(photos, clips, budget=max(2, min(len(photos), round(len(clips) * 0.75))))

    # Each clip's cut grows with its length; all cuts are then scaled toward the target, and the
    # weakest clips dropped if the video still runs long.
    cuts = {id(c): min(c.duration, max(MIN_CUT, min(MAX_CUT, c.duration * SHARE_OF_FOOTAGE))) for c in clips}
    planned = sum(cuts.values()) + PHOTO_SECONDS * len(picked)
    scale = min(1.5, target / planned) if planned else 1.0
    windows: dict[int, tuple[float, float, float]] = {}  # start, length, score
    for clip in clips:
        length = min(clip.duration, max(2.0, cuts[id(clip)] * scale))
        start, score = best_window(clip, length)
        windows[id(clip)] = (start, length, score)
    kept = sorted(clips, key=lambda c: windows[id(c)][2], reverse=True)
    while len(kept) > 2 and sum(windows[id(c)][1] for c in kept) + PHOTO_SECONDS * len(picked) > target * 1.15:
        kept.pop()

    chapters: dict[date, Chapter] = {}
    last_caption = ""
    for source in sorted([*kept, *picked], key=lambda s: s.item.taken_at):
        item = source.item
        if item.day not in chapters:
            chapters[item.day] = Chapter(title=f"{item.local:%A} {item.local.day} {item.local:%B}")
            last_caption = ""
        chapter = chapters[item.day]
        caption = " · ".join(filter(None, [item.place, time_of_day(item.local)]))
        start, length = (windows[id(source)][:2] if isinstance(source, Clip) else (0.0, PHOTO_SECONDS))
        segment = Segment(source, start, length, caption=caption if caption != last_caption else "")
        if not chapter.segments:
            segment.chapter_title = chapter.title
        chapter.segments.append(segment)
        last_caption = caption or last_caption

    return EditPlan(title=trip_title(trip), dates=trip_dates(trip), chapters=list(chapters.values()))


def trip_title(trip: Trip) -> str:
    """The two places with the most media, leaving out home (departure and return days)."""
    places = Counter(i.place for i in trip.items if i.place and not i.near_home)
    return " & ".join(place for place, _ in places.most_common(2)) or "Our trip"


def trip_dates(trip: Trip) -> str:
    first, last = trip.items[0].local, trip.items[-1].local
    if first.date() == last.date():
        return f"{last.day} {last:%B %Y}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}–{last.day} {last:%B %Y}"
    return f"{first.day} {first:%B} – {last.day} {last:%B %Y}"


def segment_label(segment: Segment) -> str:
    source: Optional[Clip | Photo] = segment.source
    detail = (f"{segment.start:.1f}+{segment.length:.1f}s" if segment.is_clip
              else f"{source.faces} face(s)")
    return f"{'clip ' if segment.is_clip else 'photo'} {source.item.filename} {detail}"
