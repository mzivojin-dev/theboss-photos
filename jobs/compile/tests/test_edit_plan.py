"""
Tests for edit_plan: which parts of clips and which photos make the Compilation.
"""
from src.edit_plan import (MAX_CUT, best_window, enough_footage, pick_photos, plan_edit, trip_dates,
                           trip_title)
from src.trips import Trip, find_trips
from tests.builders import CONSTANTA, KITCHENER, TIMISOARA, TORONTO, clip, days, item, localised, photo


def test_the_best_window_is_where_people_talk_and_move():
    start, score = best_window(clip(item("2026-07-03 08:00", TIMISOARA, video=True), loud_from=20), 5)

    assert start == 20.0
    assert score > 0.5


def test_a_trip_needs_three_clips_or_a_minute_of_footage():
    short = [clip(item("2026-03-21 18:00", None, video=True), duration=16)]
    three = [clip(item(f"2026-03-21 18:0{n}", None, video=True), duration=5) for n in range(3)]
    long = [clip(item("2026-03-21 18:00", None, video=True), duration=61)]

    assert not enough_footage(short)
    assert enough_footage(three)
    assert enough_footage(long)


def test_a_burst_keeps_its_photo_with_the_clearest_faces():
    burst = [photo(item(f"2026-07-03 08:{m:02}", TIMISOARA), face_score=s) for m, s in [(0, 0.1), (0, 0.9), (0, 0.3)]]
    burst[1].item.taken_at = burst[0].item.taken_at.replace(second=5)
    burst[2].item.taken_at = burst[0].item.taken_at.replace(second=10)

    assert pick_photos(burst, clips=[], budget=5) == [burst[1]]


def test_photos_of_a_moment_a_clip_covers_are_left_out():
    moment = item("2026-07-03 08:00", TIMISOARA, video=True)
    beside_the_clip = photo(item("2026-07-03 08:00", TIMISOARA))
    later = photo(item("2026-07-03 12:00", TIMISOARA))

    assert pick_photos([beside_the_clip, later], [clip(moment)], budget=5) == [later]


def test_photos_stay_spread_over_the_trip_and_prefer_faces():
    photos = [photo(item(f"2026-07-{d:02} {h:02}:00", TIMISOARA), face_score=0.8 if h == 14 else 0.0)
              for d in range(1, 5) for h in (10, 14)]

    picked = pick_photos(photos, clips=[], budget=4)

    assert [p.item.taken_at.day for p in picked] == [1, 2, 3, 4]
    assert all(p.face_score == 0.8 for p in picked)


def test_the_plan_has_a_chapter_per_local_day_with_its_title_on_the_first_shot():
    items = localised([item("2026-07-03 08:00", TIMISOARA, video=True), item("2026-07-03 12:00", TIMISOARA),
                       item("2026-07-04 22:30", TIMISOARA, video=True)])  # 01:30 on 5 July locally
    trip = Trip(tuple(items))

    plan = plan_edit(trip, [clip(items[0], loud_from=3), clip(items[2], loud_from=3)], [photo(items[1])])

    assert [c.title for c in plan.chapters] == ["Friday 3 July", "Sunday 5 July"]
    assert plan.chapters[0].segments[0].chapter_title == "Friday 3 July"
    assert plan.chapters[0].segments[0].caption == "Timisoara · morning"
    assert plan.chapters[0].segments[1].caption == "Timisoara · afternoon"


def test_clip_cuts_stay_within_bounds_and_the_clip():
    items = localised([item(f"2026-07-0{d} 08:00", TIMISOARA, video=True) for d in range(1, 4)])
    clips = [clip(items[0], duration=4), clip(items[1], duration=200), clip(items[2], duration=30)]

    plan = plan_edit(Trip(tuple(items)), clips, [])

    for segment in (s for c in plan.chapters for s in c.segments):
        assert segment.start + segment.length <= segment.source.duration
        assert segment.length <= MAX_CUT * 1.5


def test_the_title_names_the_two_most_photographed_places_and_the_dates():
    items = localised([item("2026-06-30 12:00", TIMISOARA), item("2026-07-01 12:00", TIMISOARA),
                       item("2026-07-20 12:00", CONSTANTA), item("2026-08-15 12:00", KITCHENER)])
    trip = Trip(tuple(items))

    assert trip_title(trip) == "Timisoara & Constanta"
    assert trip_dates(trip) == "30 June – 15 August 2026"


def test_home_does_not_name_a_trip():
    leaving = [*[item(f"2026-06-20 1{h}:00", KITCHENER) for h in range(5)], item("2026-06-20 22:00", TORONTO)]
    items = localised([*days("2026-05-01", 30, KITCHENER), *leaving,
                       *days("2026-06-21", 3, TIMISOARA, video=True), *days("2026-06-24", 2, CONSTANTA),
                       *days("2026-07-10", 3, KITCHENER)])

    [trip] = find_trips(items)

    assert trip.first_day.isoformat() == "2026-06-20"  # the departure day is part of the trip
    assert trip_title(trip) == "Timisoara & Constanta"
