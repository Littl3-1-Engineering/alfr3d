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


def _write_deck(root, kind, install="deck-1", user_id=1, day=LAST, local_from=8, local_to=17):
    """Bronze Deck reports every 5 minutes across [local_from, local_to) on `day` (local EDT = UTC-4
    in October) and the install-to-user link, as the nightly export writes them."""
    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=local_from + 4)
    stop = datetime.combine(day, datetime.min.time()) + timedelta(hours=local_to + 4)
    reports, at = [], start
    while at < stop:
        reports.append({"device_install_id": install, "observed_at": at, "network_type": kind})
        at += timedelta(minutes=5)
    (root / "bronze" / "deck_context_history" / f"date={day}").mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(reports),
        root / "bronze" / "deck_context_history" / f"date={day}" / "part-0.parquet",
    )
    (root / "bronze" / "device_location_history" / f"date={day}").mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([{"client_install_id": install, "user_id": user_id}]),
        root / "bronze" / "device_location_history" / f"date={day}" / "part-0.parquet",
    )


def _absent_history(day, hour):
    return 0 if day == LAST and 9 <= hour < 17 else 60


class TestDeckFamily:
    def test_no_bronze_is_no_deck_not_an_error(self, tmp_path):
        assert replay.load_deck(str(tmp_path)) == ({}, {})

    def test_sustained_wifi_and_cellular_become_states_like_live(self, tmp_path):
        _write_deck(tmp_path, "wifi")
        deck = replay.load_deck(str(tmp_path))
        at = datetime.combine(LAST, datetime.min.time()) + timedelta(hours=14 + 4)

        assert replay.deck_state_at(deck, 1, at).observed == {"state": "wifi"}
        assert replay.deck_state_at(deck, 2, at) is None  # someone with no Deck: no evidence

    def test_a_stale_deck_is_no_state(self, tmp_path):
        _write_deck(tmp_path, "cellular")
        deck = replay.load_deck(str(tmp_path))
        long_after = datetime.combine(LAST, datetime.min.time()) + timedelta(hours=23 + 4)

        assert replay.deck_state_at(deck, 1, long_after) is None

    def test_a_wifi_deck_explains_an_absence_away_and_a_cellular_one_does_not(self, tmp_path):
        wifi_lake = tmp_path / "wifi"
        cell_lake = tmp_path / "cell"
        for root in (wifi_lake, cell_lake):
            root.mkdir()
        _write_lake(wifi_lake, _absent_history)
        _write_lake(cell_lake, _absent_history)
        _write_deck(wifi_lake, "wifi")
        _write_deck(cell_lake, "cellular")
        window = (date(2026, 9, 28), LAST)

        # A strong discount, so a sleeping-phone explanation is enough to silence this absence.
        wifi = replay.replay_away_unusual(str(wifi_lake), *window, explained_discount=0.95)
        cell = replay.replay_away_unusual(str(cell_lake), *window, explained_discount=0.95)

        assert wifi["deck"]["flag_days_without_deck"] == 1
        assert wifi["deck"]["flag_days_with_deck"] == 0  # a sleeping phone, not an absence
        assert cell["deck"]["presence_deviations_by_deck_state"]["out"] > 0
        assert cell["deck"]["flag_days_with_deck"] == 1  # cellular never explains it away
        assert wifi["deck"]["users_with_a_reporting_deck"] == 1
        assert not any("deck" in item for item in wifi["unreconstructed"])

    def test_explained_discount_is_reported_and_sweepable(self, tmp_path):
        _write_lake(tmp_path, _absent_history)
        _write_deck(tmp_path, "wifi")

        out = replay.sweep(
            replay.replay_away_unusual,
            str(tmp_path),
            date(2026, 9, 28),
            LAST,
            "explained_discount",
            [0.0, 0.95],
        )

        # With no discount a wifi explanation changes nothing: the absence still flags.
        assert out[0]["flag_days"] == 1 and out[1]["flag_days"] == 0

    def test_a_very_surprising_absence_survives_the_default_wifi_discount(self, tmp_path):
        _write_lake(tmp_path, _absent_history)
        _write_deck(tmp_path, "wifi")

        out = replay.replay_away_unusual(str(tmp_path), date(2026, 9, 28), LAST)

        # By design: an explanation removes 70 % of the surprise, it never silences everything.
        assert out["explained_discount"] == 0.7
        assert out["deck"]["presence_deviations_by_deck_state"]["wifi"] > 0
        assert out["deck"]["flag_days_with_deck"] == 1


def _write_calendar(root, events, captured_from):
    """Silver calendar_busy and the bronze export that says when capture began (the earliest
    `created_at`), as the nightly build writes them."""
    (root / "silver" / "calendar_busy").mkdir(parents=True)
    schema = pa.schema(
        [
            pa.field("start_utc", pa.timestamp("us")),
            pa.field("end_utc", pa.timestamp("us")),
            pa.field("all_day", pa.bool_()),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(
            [{"start_utc": s, "end_utc": e, "all_day": False} for s, e in events], schema=schema
        ),
        root / "silver" / "calendar_busy" / "part-0.parquet",
    )
    (root / "bronze" / "calendar_events" / f"date={captured_from.date()}").mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([{"created_at": captured_from, "title": "x"}]),
        root / "bronze" / "calendar_events" / f"date={captured_from.date()}" / "part-0.parquet",
    )


def _utc(day, hour):
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)


class TestCalendarIsReconstructed:
    """The MySQL calendar table keeps 730 days since LF-0 (2026-10-09) and the lake exports it
    nightly, so the calendar can be replayed from the day it was first captured."""

    def _calendar(self, events, captured):
        return {"events": events, "captured_from": captured}

    def test_no_calendar_in_the_lake_is_no_history_not_an_error(self, tmp_path):
        assert replay.load_calendar(str(tmp_path)) == {"events": [], "captured_from": None}

    def test_load_reads_events_and_the_day_capture_began(self, tmp_path):
        _write_calendar(tmp_path, [(_utc(LAST, 12), _utc(LAST, 20))], datetime(2026, 9, 1, 14, 46))

        cal = replay.load_calendar(str(tmp_path))

        assert cal["events"] == [(_utc(LAST, 12), _utc(LAST, 20))]
        assert cal["captured_from"] == datetime(2026, 9, 1, 14, 46)

    def test_a_covering_event_is_a_state_and_the_hour_after_is_not(self):
        cal = self._calendar([(_utc(LAST, 12), _utc(LAST, 20))], datetime(2026, 9, 1))

        assert replay.calendar_state_at(cal, _utc(LAST, 15)).signal == "calendar.busy"
        assert replay.calendar_state_at(cal, _utc(LAST, 21)) is None

    def test_before_capture_the_calendar_is_unknown_not_free(self):
        cal = self._calendar([(_utc(LAST, 12), _utc(LAST, 20))], datetime(2026, 10, 9, 14, 46))

        assert not replay.calendar_known_at(cal, datetime(2026, 10, 1))
        assert replay.calendar_state_at(cal, datetime(2026, 10, 1)) is None
        assert replay.calendar_known_at(cal, datetime(2026, 10, 10))

    def test_events_on_a_day_count_overlaps_and_are_none_before_capture(self):
        from zoneinfo import ZoneInfo

        zone = ZoneInfo("America/Toronto")
        cal = self._calendar(
            [(_utc(LAST, 12), _utc(LAST, 20)), (_utc(LAST, 22), _utc(LAST + timedelta(1), 2))],
            datetime(2026, 9, 1),
        )

        assert replay.calendar_events_on(cal, LAST, zone) == 2
        assert replay.calendar_events_on(cal, LAST + timedelta(days=5), zone) == 0
        assert replay.calendar_events_on(cal, date(2026, 8, 30), zone) is None

    def test_a_booked_event_explains_an_absence_that_flags_without_it(self, tmp_path):
        _write_lake(tmp_path, _absent_history)
        # 12:00-22:00 UTC covers the whole absence (09:00-17:00 local is 13:00-21:00 UTC)
        _write_calendar(tmp_path, [(_utc(LAST, 12), _utc(LAST, 22))], datetime(2026, 9, 1))

        out = replay.replay_away_unusual(
            str(tmp_path), date(2026, 9, 28), LAST, explained_discount=0.95
        )

        assert out["calendar"]["flag_days_without_calendar"] == 1
        assert out["flag_days"] == 0  # a booked stretch is not an unusual absence
        assert out["calendar"]["presence_deviations_by_calendar_state"]["covering"] > 0
        assert not any("calendar" in item for item in out["unreconstructed"])

    def test_hours_before_capture_are_declared_not_treated_as_free(self, tmp_path):
        _write_lake(tmp_path, _absent_history)
        # the calendar was first captured the evening AFTER the absence being replayed
        _write_calendar(tmp_path, [], datetime(2026, 10, 9, 23))

        out = replay.replay_away_unusual(str(tmp_path), date(2026, 9, 28), LAST)

        note = next(item for item in out["unreconstructed"] if item.startswith("calendar"))
        assert "history starts 2026-10-09" in note and "unknown, not free" in note
        assert out["calendar"]["presence_deviations_by_calendar_state"]["unknown"] > 0

    def test_day_off_uses_the_real_count_of_events_that_day(self, tmp_path):
        def history(day, hour):
            return 60 if day == LAST else _worker(day, hour)

        _write_lake(tmp_path, history)
        _write_calendar(tmp_path, [(_utc(LAST, 14), _utc(LAST, 15))], datetime(2026, 9, 1))

        out = replay.replay_day_off(str(tmp_path), date(2026, 9, 14), LAST)

        assert out["calendar"]["days_with_a_known_count"] > 0
        assert out["calendar"]["events"] == 1
        # a booked day lowers confidence to the floor: never more flag-days than an empty one
        assert out["flag_days"] <= out["calendar_bounds"]["empty_calendar"]["flag_days"]
