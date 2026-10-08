"""
Tests for compilation_job.CompilationJob: which trips get a Compilation, and what is recorded.
"""
from datetime import datetime, timedelta, timezone

from src.compilation_job import CompilationJob, Made, Skipped
from src.renderer import Rendered
from tests.builders import KITCHENER, TIMISOARA, TORONTO, days, item, localised


class InMemoryStore:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.saves: list[tuple[str, str]] = []

    def get(self, trip_id):
        return self.docs.get(trip_id)

    def save(self, trip_id, fields):
        self.docs[trip_id] = fields
        self.saves.append((trip_id, fields["status"]))

    def all(self):
        return dict(self.docs)


class InMemoryVideos:
    def __init__(self):
        self.uploaded: list[str] = []

        self.deleted: list[str] = []

    def upload_file(self, path, local_path, content_type):
        self.uploaded.append(path)

    def delete(self, path):
        self.deleted.append(path)


class Maker:
    def __init__(self, outcome=None, fail_with: Exception | None = None):
        self.made: list[str] = []
        self._outcome = outcome
        self._fail_with = fail_with

    def __call__(self, trip, workdir):
        self.made.append(trip.id)
        if self._fail_with:
            raise self._fail_with
        return self._outcome or Made(
            rendered=Rendered(path=f"{workdir}/compilation.mp4", seconds=342.0,
                              chapters=[(0.0, "Timisoara"), (3.5, "Saturday 20 June")],
                              music_credits=["Jazz Aug 4 2021 by Alex McCulloch (CC0)"]),
            title="Timisoara", dates="20 June 2026", look="1080x1920 HDR HEVC (HLG)", clips=3, photos=2)


def _library(extra=()):
    return localised([*days("2026-06-01", 19, KITCHENER), *days("2026-06-20", 3, TIMISOARA, video=True),
                      *days("2026-06-23", 5, KITCHENER), *extra])


def test_a_trip_gets_a_compilation_recorded_as_ready():
    store, videos, maker = InMemoryStore(), InMemoryVideos(), Maker()

    summary = CompilationJob(store, videos, maker).run(_library())

    assert summary.made == ["2026-06-20_2026-06-22"]
    assert videos.uploaded == ["2026-06-20_2026-06-22.mp4"]
    doc = store.docs["2026-06-20_2026-06-22"]
    assert doc["status"] == "ready"
    assert doc["video_gcs_path"] == "2026-06-20_2026-06-22.mp4"
    assert doc["chapters"] == [{"start": 0.0, "title": "Timisoara"}, {"start": 3.5, "title": "Saturday 20 June"}]
    assert store.saves == [("2026-06-20_2026-06-22", "rendering"), ("2026-06-20_2026-06-22", "ready")]


def test_an_unchanged_trip_is_not_made_again():
    library, store, maker = _library(), InMemoryStore(), Maker()
    CompilationJob(store, InMemoryVideos(), Maker()).run(library)

    summary = CompilationJob(store, InMemoryVideos(), maker).run(library)

    assert maker.made == []
    assert summary.unchanged == ["2026-06-20_2026-06-22"]


def test_a_trip_is_made_again_when_its_media_changes():
    library, store, maker = _library(), InMemoryStore(), Maker()
    CompilationJob(store, InMemoryVideos(), Maker()).run(library)

    CompilationJob(store, InMemoryVideos(), maker).run(localised([*library, item("2026-06-21 18:00", TIMISOARA)]))

    assert maker.made == ["2026-06-20_2026-06-22"]


def test_a_trip_with_too_little_footage_is_recorded_as_skipped_and_not_retried():
    library, store, videos = _library(), InMemoryStore(), InMemoryVideos()
    CompilationJob(store, videos, Maker(outcome=Skipped("1 clip(s), 16s of footage"))).run(library)
    maker = Maker()

    CompilationJob(store, videos, maker).run(library)

    assert store.docs["2026-06-20_2026-06-22"]["status"] == "skipped"
    assert videos.uploaded == [] and maker.made == []


def test_a_failed_trip_is_recorded_retried_next_run_and_does_not_stop_the_others():
    library = _library([*days("2026-03-21", 1, TORONTO, video=True)])
    store = InMemoryStore()

    summary = CompilationJob(store, InMemoryVideos(), Maker(fail_with=RuntimeError("ffmpeg failed"))).run(library)
    retry = Maker()
    CompilationJob(store, InMemoryVideos(), retry).run(library)

    assert summary.failed == ["2026-03-21_2026-03-21", "2026-06-20_2026-06-22"]
    assert store.docs["2026-06-20_2026-06-22"]["status"] == "ready"
    assert retry.made == ["2026-03-21_2026-03-21", "2026-06-20_2026-06-22"]


def test_cloud_run_tasks_split_the_trips():
    library = _library([*days("2026-03-21", 1, TORONTO, video=True)])
    first, second = Maker(), Maker()

    CompilationJob(InMemoryStore(), InMemoryVideos(), first).run(library, task_index=0, task_count=2)
    CompilationJob(InMemoryStore(), InMemoryVideos(), second).run(library, task_index=1, task_count=2)

    assert first.made == ["2026-03-21_2026-03-21"]
    assert second.made == ["2026-06-20_2026-06-22"]


TRIP = "2026-06-20_2026-06-22"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class Killed(BaseException):
    """Stands in for the task being killed mid-render (out of memory): nothing gets recorded."""


def test_a_trip_another_execution_is_rendering_is_left_to_it():
    library, store, clock = _library(), InMemoryStore(), Clock()
    try:
        CompilationJob(store, InMemoryVideos(), Maker(fail_with=Killed()), now=clock).run(library)
    except Killed:
        pass
    maker = Maker()
    clock.now += timedelta(hours=1)

    summary = CompilationJob(store, InMemoryVideos(), maker, now=clock).run(library)

    assert summary.in_progress == [TRIP] and maker.made == []


def test_a_render_that_died_counts_as_an_attempt_and_is_retried():
    library, store, clock = _library(), InMemoryStore(), Clock()
    try:
        CompilationJob(store, InMemoryVideos(), Maker(fail_with=Killed()), now=clock).run(library)
    except Killed:
        pass
    clock.now += timedelta(hours=7)
    maker = Maker()

    CompilationJob(store, InMemoryVideos(), maker, now=clock).run(library)

    assert maker.made == [TRIP]
    assert store.docs[TRIP]["status"] == "ready" and store.docs[TRIP]["attempts"] == 2


def test_a_trip_is_given_up_after_two_attempts_until_its_media_changes():
    library, store = _library(), InMemoryStore()
    for _ in range(2):
        CompilationJob(store, InMemoryVideos(), Maker(fail_with=RuntimeError("ffmpeg failed"))).run(library)
    third = Maker()

    summary = CompilationJob(store, InMemoryVideos(), third).run(library)
    CompilationJob(store, InMemoryVideos(), third).run(localised([*library, item("2026-06-21 18:00", TIMISOARA)]))

    assert summary.given_up == [TRIP]
    assert third.made == [TRIP]  # only after new media
    assert store.docs[TRIP]["status"] == "ready"


def test_a_compilation_whose_trip_moved_is_superseded_and_its_video_deleted():
    library, store, videos = _library(), InMemoryStore(), InMemoryVideos()
    CompilationJob(store, videos, Maker()).run(library)

    summary = CompilationJob(store, videos, Maker()).run(localised([*library, item("2026-06-19 18:00", TIMISOARA)]))

    assert summary.made == ["2026-06-19_2026-06-22"]
    assert summary.superseded == [TRIP]
    assert videos.deleted == [f"{TRIP}.mp4"]
    assert store.docs[TRIP]["status"] == "superseded" and store.docs[TRIP]["video_gcs_path"] is None
