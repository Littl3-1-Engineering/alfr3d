"""Unit tests for common.day_context / common.timeofday -- the single
time-of-day source the mute gate, the LLM prompt, the idle-quip wind-down and
the music/mood bucketers all read.

These exercise the pure assembly logic (``_assemble`` / ``_classify``) with
explicit wake/bed/sun times, so no DB is involved.
"""

from datetime import datetime, time

import pytest

from services.common import day_context, timeofday


def dc(hour, minute=0, wake=time(7, 30), bed=time(22, 0), sunrise=(6, 44), sunset=(19, 51)):
    now = datetime(2026, 9, 3, hour, minute)  # a Thursday
    sr = (
        now.replace(hour=sunrise[0], minute=sunrise[1], second=0, microsecond=0)
        if sunrise
        else None
    )
    ss = now.replace(hour=sunset[0], minute=sunset[1], second=0, microsecond=0) if sunset else None
    return day_context._assemble(now, wake, bed, sr, ss)


class TestCoarseBucket:
    @pytest.mark.parametrize(
        "hour,expected",
        [
            (0, "night"),
            (5, "night"),
            (6, "morning"),
            (11, "morning"),
            (12, "day"),
            (17, "day"),
            (18, "evening"),
            (21, "evening"),
            (22, "night"),
        ],
    )
    def test_boundaries(self, hour, expected):
        assert timeofday.coarse_bucket(hour) == expected


class TestParts:
    def test_before_wake_is_night(self):
        assert dc(6, 0).part_of_day == "night"
        assert dc(6, 0).is_waking_hours is False

    def test_dawn_when_awake_before_sunrise(self):
        got = dc(6, 0, wake=time(5, 0), sunrise=(8, 0))
        assert got.part_of_day == "dawn"
        assert got.greeting == "Good morning"

    def test_morning_midday_afternoon_are_clock_buckets(self):
        assert dc(9).part_of_day == "morning"
        assert dc(12).part_of_day == "midday"
        assert dc(15).part_of_day == "afternoon"

    def test_evening_starts_at_sunset(self):
        assert dc(19, 30).part_of_day == "afternoon"  # just before sunset 19:51
        assert dc(20, 0).part_of_day == "evening"

    def test_wind_down_is_the_45_min_before_bed(self):
        # bed 22:00 -> wind-down window opens at 21:15
        assert dc(21, 20).part_of_day == "wind_down"
        assert dc(21, 20).in_wind_down is True
        assert dc(21, 20).is_waking_hours is True  # still technically awake
        assert dc(21, 10).part_of_day == "evening"  # one side of the boundary
        assert dc(20, 30).part_of_day == "evening"

    def test_after_bed_is_night_no_greeting(self):
        got = dc(22, 30)
        assert got.part_of_day == "night"
        assert got.greeting == ""
        assert got.minutes_to_bedtime is None

    def test_the_2200_regression(self):
        """21:59 with a 22:00 bedtime -- the exact case that shouted 'Hello
        sunshine' -> 'Good morning'. It must now read as wind-down / night."""
        assert dc(21, 59).in_wind_down is True
        assert dc(22, 1).part_of_day == "night"
        assert dc(22, 1).greeting == ""


class TestBedtimeAfterMidnight:
    def test_1am_bedtime_keeps_late_evening_awake(self):
        got = dc(23, 30, bed=time(1, 0))
        assert got.is_waking_hours is True
        assert got.part_of_day in ("evening", "wind_down")

    def test_after_1am_bedtime_is_night(self):
        got = dc(1, 30, bed=time(1, 0), wake=time(7, 30))
        assert got.part_of_day == "night"
        assert got.is_waking_hours is False


class TestCoarseMapping:
    def test_fine_parts_collapse_sanely(self):
        assert dc(9).coarse_part == "morning"
        assert dc(13).coarse_part == "day"
        assert dc(20).coarse_part == "evening"
        assert dc(21, 20).coarse_part == "night"  # wind_down -> night for music
        assert dc(23).coarse_part == "night"
