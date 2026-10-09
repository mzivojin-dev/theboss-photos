"""
Groups similar photos (bursts, retakes, near-identical shots) behind a cover, so the timeline shows
one photo with a "+N" badge. Every file is kept: this only marks which photos hide behind which.

Two photos are similar when their perceptual hashes differ in at most MAX_BITS of 64 bits, they were
taken at most MAX_GAP apart, and they have the same number of clear faces (the same spot with
different people in it stays separate). Groups chain: a photo joins the group of any similar photo
before it. The cover is the best photo: clear faces, then sharpness within the group, then exposure.

The Photo Index records this as `grouped_under` (on every photo but the cover: the cover's id) and
`group_size` (on the cover). A photo with neither is shown on its own.
"""
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

import cv2
import numpy as np

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


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def group_similar(shots: list[Shot], max_bits: int = MAX_BITS, max_gap: timedelta = MAX_GAP) -> list[list[Shot]]:
    """Groups of similar shots, each in time order. Every shot is in exactly one group."""
    shots = sorted(shots, key=lambda s: s.taken_at)
    parent = list(range(len(shots)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, shot in enumerate(shots):
        j = i - 1
        while j >= 0 and shot.taken_at - shots[j].taken_at <= max_gap:
            if shot.faces == shots[j].faces and hamming(shot.phash, shots[j].phash) <= max_bits:
                parent[find(i)] = find(j)
            j -= 1
    groups: dict[int, list[Shot]] = {}
    for i, shot in enumerate(shots):
        groups.setdefault(find(i), []).append(shot)
    return list(groups.values())


def pick_cover(group: list[Shot]) -> Shot:
    sharpest = max(s.sharpness for s in group) or 1

    def quality(s: Shot) -> float:
        return 0.5 * s.face_score + 0.4 * s.sharpness / sharpest + 0.1 * s.exposure

    return max(group, key=quality)


# --- Measuring a photo ----------------------------------------------------------------------------

def perceptual_hash(gray: np.ndarray) -> int:
    """64-bit pHash: the low frequencies of a 32x32 copy, each above or below their median."""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    bits = (low > np.median(low)).flatten()
    return int("".join("1" if bit else "0" for bit in bits), 2)


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian on a 640px copy: higher is crisper."""
    scale = 640 / max(gray.shape)
    small = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)))
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def exposure(gray: np.ndarray) -> float:
    """1 for a well-exposed photo, falling toward 0 when it is very dark or blown out."""
    mean = float(gray.mean()) / 255
    return max(0.0, 1 - max(0.0, 0.2 - mean) * 5 - max(0.0, mean - 0.85) * 5)


def measure(path: str) -> Optional[dict]:
    """What grouping needs to know about the photo at `path`, as Photo Index fields (None if unreadable)."""
    from .media_analysis import faces_in  # loads the face model, which only the real run has

    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    faces, face_score = faces_in(path)
    return {
        "similar_hash": f"{perceptual_hash(gray):016x}",
        "similar_faces": int(faces),
        "similar_face_score": float(face_score),
        "similar_sharpness": sharpness(gray),
        "similar_exposure": exposure(gray),
    }


# --- The job --------------------------------------------------------------------------------------

@dataclass
class IndexedPhoto:
    id: str
    taken_at: datetime
    preview_path: Optional[str]
    measures: Optional[dict]  # the fields `measure` returns, once computed
    grouped_under: Optional[str]
    group_size: Optional[int]


class PhotoStore(Protocol):
    def photos(self) -> list[IndexedPhoto]: ...

    def save_measures(self, photo_id: str, measures: dict) -> None: ...

    def save_group(self, photo_id: str, grouped_under: Optional[str], group_size: Optional[int]) -> None: ...


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
                m["similar_face_score"], m["similar_sharpness"], m["similar_exposure"])


def run(store: PhotoStore, previews: PreviewSource,
        measure_photo: Callable[[str], Optional[dict]] = measure) -> Summary:
    """Measure the photos not measured yet, regroup all of them, and write what changed.

    Safe to repeat: measurements are kept, and grouping is recomputed from them, so new photos
    that join an old group (or split one) are picked up."""
    photos = [p for p in store.photos() if p.preview_path]
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

    by_id = {p.id: p for p in photos if p.measures}
    groups = group_similar([_shot(p) for p in by_id.values()])
    changed = multi = hidden = 0
    for group in groups:
        cover = pick_cover(group)
        for shot in group:
            if len(group) == 1:
                wanted = (None, None)
            elif shot is cover:
                wanted = (None, len(group))
            else:
                wanted = (cover.id, None)
            photo = by_id[shot.id]
            if (photo.grouped_under, photo.group_size) != wanted:
                store.save_group(shot.id, *wanted)
                changed += 1
        if len(group) > 1:
            multi += 1
            hidden += len(group) - 1
    log.info("%d photo(s): %d measured, %d unreadable; %d group(s) hide %d photo(s); %d updated",
             len(photos), measured, unreadable, multi, hidden, changed)
    return Summary(len(photos), measured, unreadable, multi, hidden, changed)
