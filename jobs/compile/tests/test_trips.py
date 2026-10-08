"""
Tests for trips: local time, finding home, and finding trips.
"""
from datetime import date

from src.trips import find_home, find_trips
from tests.builders import CONSTANTA, KITCHENER, TIMISOARA, TORONTO, days, item, localised


def test_local_time_comes_from_where_the_item_was_taken():
    [evening] = localised([item("2026-05-03 00:48", KITCHENER)])  # 20:48 the day before in Ontario

    assert evening.day == date(2026, 5, 2)
    assert evening.local.hour == 20
    assert evening.place == "Kitchener"


def test_an_item_without_gps_takes_the_time_zone_of_the_nearest_item_in_time():
    located = item("2026-07-03 08:00", TIMISOARA)
    without_gps = item("2026-07-03 22:30", None)  # 01:30 the next day in Romania
    far_in_time = item("2026-05-01 12:00", KITCHENER)

    localised([far_in_time, located, without_gps])

    assert without_gps.time_zone == "Europe/Bucharest"
    assert without_gps.day == date(2026, 7, 4)


def test_home_is_the_place_with_the_most_days_not_the_most_photos():
    at_home = days("2026-04-01", 30, KITCHENER)  # 30 days, one photo each
    holiday = [item(f"2026-07-0{d} {h:02}:00", TIMISOARA) for d in range(1, 6) for h in range(8, 20)]  # 60 photos

    assert find_home(localised(at_home + holiday)) == (round(KITCHENER[0], 1), round(KITCHENER[1], 1))


def test_a_trip_is_the_days_away_from_home():
    items = localised([*days("2026-06-01", 20, KITCHENER),
                       *days("2026-06-21", 10, TIMISOARA), *days("2026-06-25", 2, TIMISOARA, video=True),
                       *days("2026-07-01", 10, KITCHENER)])

    [trip] = find_trips(items)

    assert (trip.first_day, trip.last_day) == (date(2026, 6, 21), date(2026, 6, 30))
    assert trip.id == "2026-06-21_2026-06-30"
    assert len(trip.clips) == 2


def test_days_without_photos_do_not_split_a_trip():
    items = localised([*days("2026-06-01", 20, KITCHENER),
                       item("2026-07-01 12:00", TIMISOARA, video=True),
                       item("2026-07-09 12:00", CONSTANTA),  # a week with no photos in between
                       *days("2026-07-20", 5, KITCHENER)])

    [trip] = find_trips(items)

    assert (trip.first_day, trip.last_day) == (date(2026, 7, 1), date(2026, 7, 9))


def test_a_day_at_home_ends_a_trip():
    items = localised([*days("2026-03-01", 30, KITCHENER),
                       item("2026-03-21 18:00", TORONTO, video=True),
                       item("2026-03-28 18:00", TORONTO, video=True)])

    assert [t.id for t in find_trips(items)] == ["2026-03-21_2026-03-21", "2026-03-28_2026-03-28"]


def test_trips_without_video_are_left_out():
    items = localised([*days("2026-06-01", 20, KITCHENER), *days("2026-06-21", 3, TIMISOARA)])

    assert find_trips(items) == []


def test_the_membership_changes_when_media_joins_a_trip():
    base = [*days("2026-06-01", 20, KITCHENER), *days("2026-06-21", 3, TIMISOARA, video=True)]
    [before] = find_trips(localised(base))

    [after] = find_trips(localised([*base, item("2026-06-22 18:00", TIMISOARA)]))

    assert before.id == after.id
    assert before.membership != after.membership
