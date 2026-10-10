"""
Tests for similar_photos: which photos are grouped, which is the cover, and what the job writes.
"""
from datetime import datetime, timedelta, timezone

import numpy as np

from src.photo_measures import perceptual_hash
from src.similar_photos import Grouping, IndexedPhoto, Shot, group_similar, pick_cover, run

START = datetime(2026, 7, 3, 8, 55, tzinfo=timezone.utc)


def shot(id: str, seconds: int = 0, phash: int = 0, faces: int = 0, face_score: float = 0.0,
         sharpness: float = 100.0, exposure: float = 1.0, pinned: bool = False) -> Shot:
    return Shot(id, START + timedelta(seconds=seconds), phash, faces, face_score, sharpness, exposure, pinned)


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


def test_a_group_does_not_drift_by_chaining_through_neighbours():
    # a~b and b~c (6 bits each), but a and c differ by 12: they are not alike, so c can't join a's group.
    a, b, c = shot("a", 0, phash=0), shot("b", 10, phash=0b111111), shot("c", 20, phash=0b111111_111111)
    assert ids(group_similar([a, b, c])) == [["a", "b"], ["c"]]


def test_a_group_does_not_stretch_past_the_time_window_by_chaining():
    groups = group_similar([shot("a", 0), shot("b", 100), shot("c", 200)])
    assert ids(groups) == [["a", "b"], ["c"]]


def test_the_cover_prefers_clear_faces_then_sharpness():
    faces = shot("faces", faces=2, face_score=0.9, sharpness=50)
    crisp = shot("crisp", faces=2, face_score=0.1, sharpness=500)
    assert pick_cover([crisp, faces]).id == "faces"
    assert pick_cover([shot("soft", sharpness=40), shot("crisp", sharpness=400)]).id == "crisp"


def test_a_blown_out_photo_loses_to_an_equally_sharp_one():
    assert pick_cover([shot("dark", exposure=0.1), shot("fine")]).id == "fine"


def test_a_cover_the_user_pinned_wins():
    assert pick_cover([shot("best", sharpness=900), shot("chosen", sharpness=1, pinned=True)]).id == "chosen"


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
        self.writes: list[dict[str, Grouping]] = []

    def photos(self):
        return self._photos

    def save_measures(self, photo_id, measures):
        self.measures_saved.append(photo_id)

    def save_groupings(self, changes):
        self.writes.append(dict(changes))

    @property
    def saved(self):
        return {pid: g for write in self.writes for pid, g in write.items()}


class Previews:
    def fetch(self, preview_path, directory):
        return preview_path


def measures(phash=0, faces=0, face_score=0.0, sharpness=100.0):
    return {"similar_hash": f"{phash:016x}", "similar_faces": faces, "similar_face_score": face_score,
            "similar_sharpness": sharpness, "similar_exposure": 1.0}


def indexed(id, seconds, measured=None, under=None, size=None, preview="p", pinned=False):
    return IndexedPhoto(id, START + timedelta(seconds=seconds), preview and f"{preview}/{id}",
                        measured, Grouping(under, size), pinned)


def test_the_job_marks_the_cover_and_the_photos_behind_it():
    store = Store([indexed("a", 0, measures(sharpness=10)), indexed("b", 5, measures(sharpness=900)),
                   indexed("c", 3600, measures())])
    summary = run(store, Previews())
    assert store.saved == {"a": Grouping(under="b"), "b": Grouping(size=2)}
    assert (summary.groups, summary.hidden, summary.changed) == (1, 1, 2)


def test_the_job_measures_only_photos_not_measured_before():
    store = Store([indexed("a", 0, measures()), indexed("b", 5)])
    seen = []
    summary = run(store, Previews(), lambda path: seen.append(path) or measures())
    assert seen == ["p/b"] and store.measures_saved == ["b"] and summary.measured == 1


def test_a_second_run_writes_nothing_and_a_photo_that_left_its_group_is_cleared():
    store = Store([indexed("a", 0, measures(sharpness=10), under="b"),
                   indexed("b", 5, measures(sharpness=900), size=2),
                   indexed("c", 7200, measures(), under="b")])
    run(store, Previews())
    assert store.saved == {"c": Grouping()}


def test_a_photo_that_can_no_longer_be_measured_is_taken_out_of_its_group():
    store = Store([indexed("a", 0, None, under="b"), indexed("b", 5, measures(), size=2)])
    summary = run(store, Previews(), lambda path: None)
    assert store.saved == {"a": Grouping(), "b": Grouping()}
    assert summary.unreadable == 1


def test_a_photo_without_a_preview_is_shown_on_its_own():
    store = Store([indexed("a", 0, None, under="b", preview=None), indexed("b", 5, measures(), size=2)])
    run(store, Previews())
    assert store.saved == {"a": Grouping(), "b": Grouping()}


def test_photos_are_un_hidden_before_others_are_hidden():
    store = Store([indexed("old", 0, measures(sharpness=900), under="gone"),
                   indexed("x", 7200, measures(sharpness=10)), indexed("y", 7205, measures(sharpness=900))])
    run(store, Previews())
    assert [set(w) for w in store.writes] == [{"old", "y"}, {"x"}]
    assert store.writes[1]["x"].under == "y"


def test_a_pinned_cover_is_kept_when_the_group_changes():
    store = Store([indexed("a", 0, measures(sharpness=900)), indexed("b", 5, measures(sharpness=1), pinned=True)])
    run(store, Previews())
    assert store.saved == {"a": Grouping(under="b"), "b": Grouping(size=2)}
