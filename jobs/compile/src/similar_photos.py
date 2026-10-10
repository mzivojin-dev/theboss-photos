"""
Groups similar photos (bursts, retakes, near-identical shots) behind a cover, so the timeline shows
one photo with a "+N" badge. Every file is kept: this only marks which photos hide behind which.

Photos in a group are all similar to each other, not just to a neighbour: every pair has perceptual
hashes within MAX_BITS of 64 bits and the same number of clear faces (the same spot with different
people in it stays separate), and the group spans at most MAX_GAP. The cover is the best photo
(clear faces, then sharpness within the group, then exposure), unless the user pinned one.

The Photo Index records this as `grouped_under` (on every photo but the cover: the cover's id) and
`group_size` (on the cover). A photo with neither is shown on its own. `cover_pinned` marks a cover
the user chose, which later runs keep.
"""
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

from .photo_measures import measure

log = logging.getLogger(__name__)

MAX_BITS = 10
MAX_GAP = timedelta(minutes=2)


@dataclass
class Shot:
    id: str
    taken_at: datetime
    phash: int
    faces: int
    face_score: float
    sharpness: float
    exposure: float
    pinned: bool = False  # the user chose this as its group's cover


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _alike(a: Shot, b: Shot, max_bits: int) -> bool:
    return a.faces == b.faces and hamming(a.phash, b.phash) <= max_bits


def group_similar(shots: list[Shot], max_bits: int = MAX_BITS, max_gap: timedelta = MAX_GAP) -> list[list[Shot]]:
    """Groups of shots that are all alike, each in time order. Every shot is in exactly one group.

    A shot joins the latest group it is alike to every member of and that began within max_gap of
    it; otherwise it starts a group. (Chaining through neighbours would let a slow drift of the
    scene, or two people swapping places, join shots that are nothing like each other.)"""
    groups: list[list[Shot]] = []
    for shot in sorted(shots, key=lambda s: s.taken_at):
        home = None
        for group in reversed(groups):
            if shot.taken_at - group[0].taken_at > max_gap:
                break  # earlier groups began even sooner
            if all(_alike(shot, member, max_bits) for member in group):
                home = group
                break
        if home is None:
            groups.append([shot])
        else:
            home.append(shot)
    return groups


def pick_cover(group: list[Shot]) -> Shot:
    pinned = [s for s in group if s.pinned]
    if pinned:
        return pinned[-1]
    sharpest = max(s.sharpness for s in group) or 1

    def quality(s: Shot) -> float:
        return 0.5 * s.face_score + 0.4 * s.sharpness / sharpest + 0.1 * s.exposure

    return max(group, key=quality)


# --- The job --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Grouping:
    """Where a photo stands: behind a cover, a cover of `size` photos, or on its own (both None)."""
    under: Optional[str] = None
    size: Optional[int] = None


@dataclass
class IndexedPhoto:
    id: str
    taken_at: datetime
    preview_path: Optional[str]
    measures: Optional[dict]  # the fields photo_measures.measure returns, once computed
    grouping: Grouping
    pinned: bool = False


class PhotoStore(Protocol):
    def photos(self) -> list[IndexedPhoto]: ...

    def save_measures(self, photo_id: str, measures: dict) -> None: ...

    def save_groupings(self, changes: dict[str, Grouping]) -> None: ...


class PreviewSource(Protocol):
    def fetch(self, preview_path: str, directory: str) -> Optional[str]: ...


@dataclass(frozen=True)
class Summary:
    photos: int
    measured: int
    unreadable: int
    groups: int  # groups of 2 or more
    hidden: int  # photos behind a cover
    changed: int  # photos whose grouping fields were written


def _shot(photo: IndexedPhoto) -> Shot:
    m = photo.measures
    return Shot(photo.id, photo.taken_at, int(m["similar_hash"], 16), m["similar_faces"],
                m["similar_face_score"], m["similar_sharpness"], m["similar_exposure"], photo.pinned)


def run(store: PhotoStore, previews: PreviewSource,
        measure_photo: Callable[[str], Optional[dict]] = measure) -> Summary:
    """Measure the photos not measured yet, regroup all of them, and write what changed.

    Safe to repeat: measurements are kept, and grouping is recomputed from them, so new photos
    that join an old group (or split one) are picked up. A photo that can't be measured is shown
    on its own. Photos are un-hidden before others are hidden, so a run that stops half way never
    leaves a photo hidden behind a cover that isn't there."""
    everything = store.photos()
    photos = [p for p in everything if p.preview_path]
    measured = unreadable = 0
    with tempfile.TemporaryDirectory() as directory:
        for photo in photos:
            if photo.measures:
                continue
            local = previews.fetch(photo.preview_path, directory)
            photo.measures = measure_photo(local) if local else None
            if local and os.path.exists(local):
                os.remove(local)
            if photo.measures:
                store.save_measures(photo.id, photo.measures)
                measured += 1
            else:
                unreadable += 1
                log.warning("Could not measure %s (%s)", photo.id, photo.preview_path)

    wanted: dict[str, Grouping] = {}
    for p in everything:
        if not p.measures or not p.preview_path:
            wanted[p.id] = Grouping()  # nothing to group it by: shown on its own
    by_id = {p.id: p for p in photos if p.measures}
    multi = hidden = 0
    for group in group_similar([_shot(p) for p in by_id.values()]):
        cover = pick_cover(group)
        for shot in group:
            if len(group) == 1:
                wanted[shot.id] = Grouping()
            elif shot is cover:
                wanted[shot.id] = Grouping(size=len(group))
            else:
                wanted[shot.id] = Grouping(under=cover.id)
        if len(group) > 1:
            multi += 1
            hidden += len(group) - 1

    current = {p.id: p.grouping for p in everything}
    changes = {pid: g for pid, g in wanted.items() if current[pid] != g}
    store.save_groupings({pid: g for pid, g in changes.items() if g.under is None})
    store.save_groupings({pid: g for pid, g in changes.items() if g.under is not None})
    log.info("%d photo(s): %d measured, %d unreadable; %d group(s) hide %d photo(s); %d updated",
             len(photos), measured, unreadable, multi, hidden, len(changes))
    return Summary(len(photos), measured, unreadable, multi, hidden, len(changes))
