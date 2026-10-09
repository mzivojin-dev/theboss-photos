"""
Tests for similar_photos: which photos are grouped, which is the cover, and what the job writes.
"""
from datetime import datetime, timedelta, timezone

import numpy as np

from src.similar_photos import IndexedPhoto, Shot, group_similar, perceptual_hash, pick_cover, run

START = datetime(2026, 7, 3, 8, 55, tzinfo=timezone.utc)


def shot(id: str, seconds: int = 0, phash: int = 0, faces: int = 0, face_score: float = 0.0,
         sharpness: float = 100.0, exposure: float = 1.0) -> Shot:
    return Shot(id, START + timedelta(seconds=seconds), phash, faces, face_score, sharpness, exposure)


def ids(groups):
    return sorted(sorted(s.id for s in g) for g in groups)


def test_near_identical_photos_taken_close_together_are_one_group():
    groups = group_similar([shot("a", 0), shot("b", 5, phash=0b1111), shot("c", 90)])
    assert ids(groups) == [["a", "b", "c"]]


def test_photos_too_different_or_too_far_apart_in_time_stay_apart():
    groups = group_similar([shot("a", 0), shot("b", 5, phash=(1 << 11) - 1), shot("c", 600)])
    assert ids(groups) == [["a"], ["b"], ["c"]]


def test_the_same_spot_with_a_different_number_of_faces_stays_apart():
    groups = group_similar([shot("a", 0, faces=1), shot("b", 5, faces=2)])
    assert ids(groups) == [["a"], ["b"]]


def test_similarity_chains_through_the_photo_before():
    # a-b and b-c are close in time, a-c is not (but b links them).
    groups = group_similar([shot("a", 0), shot("b", 100), shot("c", 200)])
    assert ids(groups) == [["a", "b", "c"]]


def test_the_cover_prefers_clear_faces_then_sharpness():
    faces = shot("faces", faces=2, face_score=0.9, sharpness=50)
    crisp = shot("crisp", faces=2, face_score=0.1, sharpness=500)
    assert pick_cover([crisp, faces]).id == "faces"
    assert pick_cover([shot("soft", sharpness=40), shot("crisp", sharpness=400)]).id == "crisp"


def test_a_blown_out_photo_loses_to_an_equally_sharp_one():
    assert pick_cover([shot("dark", exposure=0.1), shot("fine")]).id == "fine"


def test_the_hash_is_the_same_for_a_slightly_brighter_copy_and_differs_for_another_picture():
    rng = np.random.default_rng(1)
    picture = (rng.random((120, 160)) * 200).astype(np.uint8)
    brighter = np.clip(picture.astype(int) + 10, 0, 255).astype(np.uint8)
    other = (rng.random((120, 160)) * 200).astype(np.uint8)
    assert (perceptual_hash(picture) ^ perceptual_hash(brighter)).bit_count() <= 4
    assert (perceptual_hash(picture) ^ perceptual_hash(other)).bit_count() > 10


class Store:
    def __init__(self, photos):
        self._photos = photos
        self.measures_saved = []
        self.groups_saved = {}

    def photos(self):
        return self._photos

    def save_measures(self, photo_id, measures):
        self.measures_saved.append(photo_id)

    def save_group(self, photo_id, grouped_under, group_size):
        self.groups_saved[photo_id] = (grouped_under, group_size)


class Previews:
    def fetch(self, preview_path, directory):
        return preview_path


def measures(phash=0, faces=0, face_score=0.0, sharpness=100.0):
    return {"similar_hash": f"{phash:016x}", "similar_faces": faces, "similar_face_score": face_score,
            "similar_sharpness": sharpness, "similar_exposure": 1.0}


def indexed(id, seconds, measured=None, grouped_under=None, group_size=None, preview="p"):
    return IndexedPhoto(id, START + timedelta(seconds=seconds), preview and f"{preview}/{id}",
                        measured, grouped_under, group_size)


def test_the_job_marks_the_cover_and_the_photos_behind_it():
    store = Store([indexed("a", 0, measures(sharpness=10)), indexed("b", 5, measures(sharpness=900)),
                   indexed("c", 3600, measures())])
    summary = run(store, Previews())
    assert store.groups_saved == {"a": ("b", None), "b": (None, 2)}
    assert (summary.groups, summary.hidden, summary.changed) == (1, 1, 2)


def test_the_job_measures_only_photos_not_measured_before():
    store = Store([indexed("a", 0, measures()), indexed("b", 5)])
    seen = []
    summary = run(store, Previews(), lambda path: seen.append(path) or measures())
    assert seen == ["p/b"] and store.measures_saved == ["b"] and summary.measured == 1


def test_a_second_run_writes_nothing_and_a_photo_that_left_its_group_is_cleared():
    store = Store([indexed("a", 0, measures(sharpness=10), grouped_under="b"),
                   indexed("b", 5, measures(sharpness=900), group_size=2),
                   indexed("c", 7200, measures(), grouped_under="b")])
    run(store, Previews())
    assert store.groups_saved == {"c": (None, None)}


def test_unreadable_photos_are_counted_and_left_out_of_grouping():
    store = Store([indexed("a", 0), indexed("b", 5, measures()), indexed("video", 6, preview=None)])
    summary = run(store, Previews(), lambda path: None)
    assert summary.unreadable == 1 and store.groups_saved == {}
