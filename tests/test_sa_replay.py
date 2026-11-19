"""Tests for the replay harness (sa/replay.py): the report format, the walk-forward promise, and
the rule that history that cannot be reconstructed is declared, never invented.

Synthetic lakes with a known answer: an office worker who is out 09-17 on weekdays, then one
weekday spent out when usually home / at home when usually out.
"""

from datetime import date, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import replay

FIRST = date(2026, 8, 3)  # a Monday
LAST = date(2026, 10, 9)  # a Friday


def _write_lake(root, home_minutes):
    """home_minutes(day, hour) -> minutes home; one presence interval per local day."""
    grid, intervals = [], []
    day = FIRST
    while day <= LAST:
        for hour in range(24):
            grid.append(
                {
                    "user_id": 1,
                    "username": "athos",
                    "bucket_utc": datetime.combine(day, datetime.min.time())
                    + timedelta(hours=hour + 4),
                    "date_local": day,
                    "hour_local": hour,
                    "dow_local": day.weekday(),
                    "minutes_home": float(home_minutes(day, hour)),
                    "observed": True,
                }
            )
        midnight = datetime.combine(day, datetime.min.time()) + timedelta(hours=4)
        for hour in range(24):
            if home_minutes(day, hour) > 0:
                start = midnight + timedelta(hours=hour)
                intervals.append(
                    {
                        "user_id": 1,
                        "user_type": "owner",
                        "start_utc": start,
                        "end_utc": start + timedelta(minutes=55),
                        "sightings": 55,
                    }
                )
        day += timedelta(days=1)
    (root / "gold" / "presence_grid").mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(grid), root / "gold" / "presence_grid" / "part-0.parquet")
    (root / "silver" / "presence_intervals").mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(intervals), root / "silver" / "presence_intervals" / "part-0.parquet"
    )
    return str(root)


def _worker(day, hour):
    if day.weekday() < 5 and 9 <= hour < 17:
        return 0
    return 60


@pytest.fixture
def lake_out_on_a_home_day(tmp_path):
    """A routine office worker, except the last Friday: out 09-17 is replaced by out 09-15."""
    return _write_lake(tmp_path, _worker)


class TestReport:
    def _rows(self):
        at = datetime(2026, 10, 1, 10, 30)
        return [
            {"subject": 1, "at": at, "flagged": True, "bits": 4.0, "confidence": 0.5},
            {
                "subject": 1,
                "at": at + timedelta(hours=1),
                "flagged": True,
                "bits": 5.0,
                "confidence": 0.5,
            },
            {
                "subject": 1,
                "at": at + timedelta(days=1),
                "flagged": False,
                "bits": None,
                "confidence": None,
            },
            {"subject": 2, "at": at, "flagged": False, "bits": None, "confidence": None},
        ]

    def test_flag_days_count_days_not_hours(self):
        out = replay.report("x", "layer2", date(2026, 10, 1), date(2026, 10, 2), self._rows())

        assert out["evaluations"] == 4 and out["flagged"] == 2
        assert out["flag_days"] == 1  # two flagged hours on one day is one flag-day
        assert out["observed_days"] == 3
        assert out["flag_days_per_14"] == pytest.approx(14.0 / 3, abs=1e-3)
        assert out["by_subject"]["1"] == {
            "observed_days": 2,
            "flag_days": 1,
            "flag_days_per_14": 7.0,
        }

    def test_nothing_observed_is_none_not_zero(self):
        out = replay.report("x", "layer1", date(2026, 10, 1), date(2026, 10, 2), [])

        assert out["flag_days_per_14"] is None
        assert out["observed_days"] == 0

    def test_unreconstructed_inputs_are_carried_on_the_report(self):
        out = replay.report("x", "layer2", date(2026, 10, 1), date(2026, 10, 1), [], ["calendar"])

        assert out["unreconstructed"] == ["calendar"]


class TestReplays:
    def test_a_routine_history_flags_nothing(self, lake_out_on_a_home_day):
        out = replay.replay_away_unusual(lake_out_on_a_home_day, date(2026, 9, 28), LAST)

        assert out["flag_days"] == 0
        assert out["evaluations"] > 0

    def test_away_unusual_flags_the_one_absence_and_declares_what_it_could_not_see(self, tmp_path):
        absent = LAST

        def history(day, hour):
            if day == absent and 9 <= hour < 17:
                return 0
            if day.weekday() < 5 and day != absent:
                return 60  # a home worker, every weekday
            return 60

        lake = _write_lake(tmp_path, history)
        out = replay.replay_away_unusual(lake, date(2026, 9, 28), LAST)

        assert out["flag_days"] == 1
        assert out["by_subject"]["1"]["flag_days"] == 1
        # Never invented: the report says which inputs the replay did not have.
        assert any("calendar" in item for item in out["unreconstructed"])
        assert any("deck" in item for item in out["unreconstructed"])

    def test_day_off_reports_both_calendar_bounds(self, tmp_path):
        day_home = LAST  # a Friday spent at home by someone who is normally out

        def history(day, hour):
            if day == day_home:
                return 60
            return _worker(day, hour)

        out = replay.replay_day_off(_write_lake(tmp_path, history), date(2026, 9, 14), LAST)

        bounds = out["calendar_bounds"]
        assert set(bounds) == {"unknown", "empty_calendar", "booked_calendar"}
        # A booked calendar can only lower confidence, never add flags.
        assert bounds["booked_calendar"]["flag_days"] <= bounds["empty_calendar"]["flag_days"]
        assert bounds["unknown"]["flag_days"] == bounds["empty_calendar"]["flag_days"]
        assert any("calendar" in item for item in out["unreconstructed"])

    def test_replay_reads_the_lake_and_nothing_else(self, lake_out_on_a_home_day, monkeypatch):
        # No database, no network: a replay must work with the lake directory alone.
        import socket

        def refuse(*args, **kwargs):
            raise AssertionError("replay opened a network connection")

        monkeypatch.setattr(socket, "create_connection", refuse)
        out = replay.run(lake_out_on_a_home_day, date(2026, 9, 28), LAST, ["stay"])

        assert (
            out[0]["name"] == "stay_profile"
        )  # the learner's own name; the registry key is "stay"


class TestSweepAndRun:
    def test_sweep_never_changes_the_live_constant(self, tmp_path):
        from services.service_sa.sa.learners import day_off

        before = day_off.CORROBORATION_FLOOR
        lake = _write_lake(tmp_path, _worker)
        out = replay.sweep(
            replay.replay_day_off, lake, date(2026, 9, 14), LAST, "corroboration_floor", [0.3, 1.0]
        )

        assert [row["value"] for row in out] == [0.3, 1.0]
        assert day_off.CORROBORATION_FLOOR == before == day_off.RULE.corroboration_floor

    def test_unknown_replay_name_is_an_error(self, lake_out_on_a_home_day):
        with pytest.raises(ValueError, match="unknown replay"):
            replay.run(lake_out_on_a_home_day, date(2026, 9, 28), LAST, ["nope"])

    def test_default_window_is_the_last_complete_days(self):
        start, end = replay.default_window(today=date(2026, 11, 19), days=28)

        assert end == date(2026, 11, 18)
        assert (end - start).days + 1 == 28


class TestStayReplayDeclaresItsHindsight:
    def test_stay_report_says_it_replays_todays_bridge(self, tmp_path):
        lake = _write_lake(tmp_path, _worker)
        out = replay.replay_stay(lake, date(2026, 9, 28), LAST)

        assert any("bridge" in item for item in out["unreconstructed"])
