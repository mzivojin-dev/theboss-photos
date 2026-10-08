"""
Tests for make_compilation.CompilationMaker: a file that can't be read is left out of the trip.
"""
from src import make_compilation
from src.compilation_job import Skipped
from src.make_compilation import CompilationMaker
from src.trips import Trip
from tests.builders import TIMISOARA, clip, item, localised


class AllThere:
    def fetch(self, media, directory):
        return f"{directory}/{media.id}"


def test_an_unreadable_clip_is_left_out_instead_of_failing_the_trip(monkeypatch):
    items = localised([item(f"2026-07-0{d} 08:00", TIMISOARA, video=True) for d in range(1, 4)])
    corrupt = items[1]

    def analyse_clip(media, path):
        if media is corrupt:
            raise RuntimeError("ffprobe failed: moov atom not found")
        return clip(media, duration=10)

    monkeypatch.setattr(make_compilation, "analyse_clip", analyse_clip)

    outcome = CompilationMaker(AllThere())(Trip(tuple(items)), "/tmp")

    # Two readable 10 s clips are below the minimum, so the trip is skipped, not failed.
    assert outcome == Skipped("2 clip(s), 20s of footage")
