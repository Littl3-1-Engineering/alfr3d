"""Tests for service_sa/sa/silver.py: the silver and gold layers (LF-2).

Each test builds a small synthetic bronze lake in tmp_path, runs the real DuckDB build over it,
and reads the Parquet it wrote. The scenarios encode what the household's real data taught us
(see the module docstring): phones are presence, hardware is not, one person can have several
phone ids, short gaps are merged and counted, stale last_online values are ignored, and an hour
the collector didn't run is "unobserved", not "away".
"""

from datetime import date, datetime, timedelta

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import silver

T0 = datetime(2026, 10, 5, 12, 0)  # 08:00 EDT


def _write(lake, layer_path, rows, day):
    out = lake / layer_path / f"date={day}"
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), out / "part-0.parquet")


def _bronze(lake, table, rows, ts_field):
    """Write rows partitioned by the UTC day of ts_field, like sa/lake.py does."""
    by_day = {}
    for row in rows:
        by_day.setdefault(row[ts_field].date(), []).append(row)
    for day, day_rows in by_day.items():
        _write(lake, f"bronze/{table}", day_rows, day.isoformat())


def _snapshot(lake, table, rows, day="2026-10-05"):
    _write(lake, f"bronze/_snapshots/{table}", rows, day)


def _history_row(sighting, device_id, user_id, device_type, name="dev"):
    """A device_history row for one sighting: the trigger logs OLD values, so last_online is the
    sighting and the row is stamped about a minute after it."""
    return {
        "device_id": device_id,
        "name": name,
        "timestamp": sighting + timedelta(minutes=1),
        "last_online": sighting,
        "device_type": device_type,
        "user_id": user_id,
    }


def _sensor_row(sensor_id, value, recorded_at):
    return {"smarthome_device_id": sensor_id, "value": value, "recorded_at": recorded_at}


def _minutes(start, count, step=1):
    return [start + timedelta(minutes=i * step) for i in range(count)]


@pytest.fixture
def lake(tmp_path):
    """Two people, a system user, an unclaimed catch-all; phones and hardware."""
    _snapshot(
        tmp_path,
        "user_types",
        [{"id": 1, "type": "alfr3d"}, {"id": 2, "type": "owner"}, {"id": 3, "type": "guest"}],
    )
    _snapshot(
        tmp_path,
        "user",
        [
            {"id": 1, "username": "athos", "type": 2},
            {"id": 2, "username": "alfr3d", "type": 1},
            {"id": 3, "username": "unknown", "type": 3},
            {"id": 6, "username": "visitor", "type": 3},
        ],
    )
    rows = []
    # Athos's phone, id 10: 12:00-12:30 (31 sightings), then a 60 min gap.
    rows += [_history_row(t, 10, 1, 5) for t in _minutes(T0, 31)]
    # The same phone after a MAC rotation, id 11: 13:30-13:40.
    rows += [_history_row(t, 11, 1, 5) for t in _minutes(T0 + timedelta(minutes=90), 11)]
    # A 20 min nap on id 11 (within the 45 min gap): 14:00, then 14:20.
    rows += [_history_row(T0 + timedelta(minutes=120), 11, 1, 5)]
    rows += [_history_row(T0 + timedelta(minutes=140), 11, 1, 5)]
    # Athos's laptop (hardware, type 2): on all afternoon, every 10 min, except 15:00-16:00 UTC.
    for t in _minutes(T0, 37, step=10):
        if not (T0 + timedelta(hours=3) <= t < T0 + timedelta(hours=4)):
            rows.append(_history_row(t, 20, 1, 2, "laptop"))
    # The system user and the catch-all each own a phone-typed device: neither is a person.
    rows += [_history_row(t, 30, 2, 5) for t in _minutes(T0, 5)]
    rows += [_history_row(t, 31, 3, 5) for t in _minutes(T0, 5)]
    # A visitor, present for ten minutes only.
    rows += [_history_row(t, 40, 6, 3) for t in _minutes(T0 + timedelta(minutes=30), 10)]
    # A stale carry-over, shaped like the real ones: a row logged now whose OLD.last_online is a
    # sighting from long before the collector existed (a retired phone's last-seen date).
    stale = _history_row(T0 + timedelta(minutes=5), 10, 1, 5)
    stale["last_online"] = datetime(2023, 7, 13, 12, 0)
    rows.append(stale)
    _bronze(tmp_path, "device_history", rows, "timestamp")
    # The newest sighting of device 11 is only in the device snapshot, not yet in history.
    _snapshot(
        tmp_path,
        "device",
        [
            {
                "id": 11,
                "user_id": 1,
                "device_type": 5,
                "name": "phone",
                "last_online": T0 + timedelta(minutes=141),
            }
        ],
    )
    return tmp_path


def _read(lake, layer, table):
    path = lake / layer / table / "part-0.parquet"
    return duckdb.connect().execute(f"SELECT * FROM read_parquet('{path}')").fetchall(), [
        d[0] for d in duckdb.connect().execute(f"SELECT * FROM read_parquet('{path}')").description
    ]


def _rows(lake, layer, table):
    data, cols = _read(lake, layer, table)
    return [dict(zip(cols, r)) for r in data]


def _build(lake, **kwargs):
    return silver.build(str(lake), tz="America/Toronto", today=date(2026, 10, 6), **kwargs)


class TestPresenceIntervals:
    def test_phone_sightings_become_intervals_and_hardware_is_not_presence(self, lake):
        _build(lake)

        rows = [r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1]

        assert [(r["start_utc"], r["end_utc"]) for r in rows] == [
            (T0, T0 + timedelta(minutes=30)),
            (T0 + timedelta(minutes=90), T0 + timedelta(minutes=141)),
        ]
        assert all(r["source"] == "wifi_phone" for r in rows)

    def test_one_person_across_rotated_phone_ids_is_one_timeline(self, lake):
        _build(lake)

        second = [r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1][1]

        # Device 11 only; but the first interval is device 10, and both are the same person.
        assert second["devices"] == 1
        assert second["sightings"] == 11 + 2 + 1  # 11 sightings, the nap pair, the snapshot one

    def test_short_gaps_are_merged_and_counted_not_hidden(self, lake):
        _build(lake)

        second = [r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1][1]

        # 13:40 -> 14:00 (20 min) and 14:00 -> 14:20 (20 min) are inside the 45 min threshold;
        # 14:20 -> 14:21 (snapshot sighting) is 1 min.
        assert second["short_gaps_merged"] == 2

    def test_snapshot_adds_the_newest_sighting(self, lake):
        _build(lake)

        last = [r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1][-1]

        assert last["end_utc"] == T0 + timedelta(minutes=141)

    def test_system_user_and_unknown_catch_all_are_not_people(self, lake):
        _build(lake)

        users = {r["user_id"] for r in _rows(lake, "silver", "presence_intervals")}

        assert users == {1, 6}

    def test_stale_last_online_from_before_the_collector_is_ignored(self, lake):
        _build(lake)

        starts = [r["start_utc"] for r in _rows(lake, "silver", "presence_intervals")]

        assert min(starts) == T0

    def test_a_gap_beyond_the_threshold_starts_a_new_interval(self, lake):
        # 12:30 -> 13:30 is 60 min > 45.
        _build(lake)
        assert (
            len([r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1]) == 2
        )

        _build(lake, gap_minutes=90)  # a looser threshold merges them
        assert (
            len([r for r in _rows(lake, "silver", "presence_intervals") if r["user_id"] == 1]) == 1
        )

    def test_local_time_follows_dst(self, tmp_path):
        _snapshot(tmp_path, "user_types", [{"id": 2, "type": "owner"}])
        _snapshot(tmp_path, "user", [{"id": 1, "username": "athos", "type": 2}])
        winter, summer = datetime(2026, 2, 1, 15, 0), datetime(2026, 7, 1, 15, 0)
        _bronze(
            tmp_path,
            "device_history",
            [_history_row(winter, 1, 1, 5), _history_row(summer, 1, 1, 5)],
            "timestamp",
        )

        _build(tmp_path)
        rows = _rows(tmp_path, "silver", "presence_intervals")

        assert rows[0]["start_local"] == datetime(2026, 2, 1, 10, 0)  # EST, UTC-5
        assert rows[1]["start_local"] == datetime(2026, 7, 1, 11, 0)  # EDT, UTC-4


class TestDeviceSessions:
    def test_hardware_is_kept_here_with_its_own_sessions(self, lake):
        _build(lake)

        laptop = [r for r in _rows(lake, "silver", "device_sessions") if r["device_id"] == 20]

        # On from 12:00 to 15:00 (36 sightings each 10 min minus the 15:00-16:00 hour), then 16:00.
        assert len(laptop) == 2
        assert laptop[0]["device_type"] == 2 and laptop[0]["name"] == "laptop"


class TestEventsClean:
    def _events(self, lake, exclusions):
        _bronze(
            lake,
            "household_events",
            [
                {"id": 1, "event_type": "iot", "subject_type": "device", "subject_id": "60",
                 "verb": "set", "message": "m", "source_service": "api",
                 "occurred_at": datetime(2026, 10, 5, 12, 0, 30)},
                {"id": 2, "event_type": "iot", "subject_type": "device", "subject_id": "7",
                 "verb": "turned_on", "message": "m", "source_service": "api",
                 "occurred_at": datetime(2026, 10, 5, 12, 1, 10)},
                {"id": 3, "event_type": "info", "subject_type": "user", "subject_id": "1",
                 "verb": "came_online", "message": "m", "source_service": "user",
                 "occurred_at": datetime(2026, 10, 5, 12, 1, 30)},
                {"id": 4, "event_type": "iot", "subject_type": "device", "subject_id": "60",
                 "verb": "set", "message": "m", "source_service": "api",
                 "occurred_at": datetime(2026, 10, 5, 13, 0)},
            ],
            "occurred_at",
        )  # fmt: skip
        _build(lake, exclusions=exclusions)
        return {r["id"] for r in _rows(lake, "silver", "events_clean")}

    def test_exclusion_drops_only_matching_event_types_inside_the_window(self, lake):
        window = datetime(2026, 10, 5, 12, 0), datetime(2026, 10, 5, 12, 5)

        kept = self._events(lake, [("household_events", "iot", None, *window)])

        # ids 1 and 2 (iot, inside) dropped; the info event inside the window and the iot event
        # outside it both stay.
        assert kept == {3, 4}

    def test_exclusion_can_narrow_to_one_subject(self, lake):
        window = datetime(2026, 10, 5, 12, 0), datetime(2026, 10, 5, 12, 5)

        kept = self._events(lake, [("household_events", "iot", "60", *window)])

        assert kept == {2, 3, 4}

    def test_no_exclusions_keeps_everything(self, lake):
        assert self._events(lake, []) == {1, 2, 3, 4}


class TestSensors:
    def test_retired_ids_resolve_through_aliases_to_one_stable_series(self, lake):
        _snapshot(
            lake,
            "smarthome_devices",
            [
                {"id": 100, "name": "Temperature", "source": "esphome",
                 "esp_entity_id": "node.local:555", "ha_entity_id": None, "st_device_id": None}
            ],
        )  # fmt: skip
        _bronze(
            lake,
            "smarthome_sensor_history",
            [
                _sensor_row(90, 20.0, datetime(2026, 9, 1, 12, 1)),
                _sensor_row(100, 22.0, datetime(2026, 10, 5, 12, 2)),
                _sensor_row(100, 24.0, datetime(2026, 10, 5, 12, 9)),
                _sensor_row(555, 1.0, datetime(2026, 10, 5, 12, 3)),
            ],
            "recorded_at",
        )  # fmt: skip

        _build(lake, aliases={90: "node.local:Temperature"})
        rows = _rows(lake, "silver", "sensor_15m")

        by_key = {}
        for r in rows:
            by_key.setdefault(r["sensor_key"], []).append(r)
        assert set(by_key) == {"node.local:Temperature", "id:555"}  # unknown id falls back
        temperature = by_key["node.local:Temperature"]
        assert [r["n"] for r in temperature] == [1, 2]  # Sept via alias, Oct via snapshot
        assert temperature[1]["mean"] == 23.0 and temperature[1]["max"] == 24.0


class TestCalendarBusy:
    def test_busy_intervals_without_titles_or_notes(self, lake):
        _bronze(
            lake,
            "calendar_events",
            [
                {"title": "Secret meeting", "notes": "private", "address": "1 Main St",
                 "conference_uri": None, "start_time": datetime(2026, 10, 5, 14, 0),
                 "end_time": datetime(2026, 10, 5, 15, 0)},
                {"title": "Holiday", "notes": None, "address": None, "conference_uri": "meet",
                 "start_time": datetime(2026, 10, 6, 4, 0),
                 "end_time": datetime(2026, 10, 7, 4, 0)},
            ],
            "start_time",
        )  # fmt: skip

        _build(lake)
        rows = _rows(lake, "silver", "calendar_busy")

        assert "title" not in rows[0] and "notes" not in rows[0]
        assert [(r["all_day"], r["has_address"], r["has_conference"]) for r in rows] == [
            (False, True, False),
            (True, False, True),
        ]


class TestDayContext:
    def test_ontario_statutory_holidays_2026(self):
        holidays = silver.ontario_holidays(2026)

        assert holidays[date(2026, 2, 16)] == "Family Day"
        assert holidays[date(2026, 4, 3)] == "Good Friday"  # Easter is April 5
        assert holidays[date(2026, 5, 18)] == "Victoria Day"
        assert holidays[date(2026, 7, 1)] == "Canada Day"
        assert holidays[date(2026, 9, 7)] == "Labour Day"
        assert holidays[date(2026, 10, 12)] == "Thanksgiving"
        assert holidays[date(2026, 12, 25)] == "Christmas Day"
        assert holidays[date(2026, 12, 26)] == "Boxing Day"
        assert len(holidays) == 9

    def test_victoria_day_is_the_monday_before_may_25(self):
        assert silver.ontario_holidays(2027)[date(2027, 5, 24)] == "Victoria Day"  # a Monday
        assert silver.ontario_holidays(2025)[date(2025, 5, 19)] == "Victoria Day"

    def test_spine_rows(self):
        rows = {
            r["date"]: r for r in silver.day_context_rows(date(2026, 10, 9), date(2026, 10, 12))
        }

        assert rows[date(2026, 10, 9)]["dow"] == 4 and not rows[date(2026, 10, 9)]["is_weekend"]
        assert rows[date(2026, 10, 10)]["is_weekend"]
        assert (
            rows[date(2026, 10, 12)]["is_holiday"]
            and rows[date(2026, 10, 12)]["season"] == "autumn"
        )

    def test_season_boundaries(self):
        assert [silver._season(m) for m in (12, 3, 6, 9)] == [
            "winter",
            "spring",
            "summer",
            "autumn",
        ]


class TestGold:
    def test_presence_grid_minutes_zero_fill_and_observed(self, lake):
        _build(lake)

        grid = {
            r["bucket_utc"]: r for r in _rows(lake, "gold", "presence_grid") if r["user_id"] == 1
        }

        assert grid[T0]["minutes_home"] == pytest.approx(30)  # 12:00-12:30
        # The 13:30 interval runs on through the two 20-minute naps to 14:21, so it splits
        # across two hours: 30 minutes in the 13:00 hour, 21 in the 14:00 hour.
        assert grid[T0 + timedelta(hours=1)]["minutes_home"] == pytest.approx(30)
        assert grid[T0 + timedelta(hours=2)]["minutes_home"] == pytest.approx(21)
        # 15:00-16:00 UTC: nobody home AND the collector wrote nothing (the laptop was quiet too).
        quiet = grid[T0 + timedelta(hours=3)]
        assert quiet["minutes_home"] == 0 and quiet["observed"] is False
        assert grid[T0]["observed"] is True
        assert grid[T0]["hour_local"] == 8 and grid[T0]["dow_local"] == 0  # Mon 08:00 EDT

    def test_the_hour_still_in_progress_at_the_horizon_is_not_an_observation(self, lake):
        """The export runs partway through an hour. Counted as observed, it would read as 'away'
        for everyone (no one can have 30 minutes at home yet) and bias every learner trained on it.
        """
        _build(lake)

        grid = [r for r in _rows(lake, "gold", "presence_grid") if r["user_id"] == 1]
        last = max(grid, key=lambda r: r["bucket_utc"])

        # The fixture's newest collector row (the laptop's last sighting) is in the 18:00 UTC hour.
        assert last["bucket_utc"] == datetime(2026, 10, 5, 18, 0)
        assert last["observed"] is False
        earlier = [r for r in grid if r["bucket_utc"] < last["bucket_utc"]]
        assert any(r["observed"] for r in earlier)

    def test_presence_grid_only_covers_each_persons_own_span(self, lake):
        _build(lake)

        visitor = [r for r in _rows(lake, "gold", "presence_grid") if r["user_id"] == 6]

        assert min(r["bucket_utc"] for r in visitor) == T0 + timedelta(minutes=30) - timedelta(
            minutes=30
        )
        assert visitor[0]["bucket_utc"] >= T0

    def test_daily_rhythm(self, lake):
        _build(lake)

        day = [
            r for r in _rows(lake, "gold", "daily_rhythm")
            if r["user_id"] == 1 and r["date_local"] == date(2026, 10, 5)
        ][0]  # fmt: skip

        assert day["first_seen_local"] == datetime(2026, 10, 5, 8, 0)
        assert day["last_seen_local"] == datetime(2026, 10, 5, 10, 21)
        assert day["n_intervals"] == 2
        assert day["longest_absence_min"] == 60
        assert day["minutes_home"] == pytest.approx(30 + 51)
        assert day["dow_local"] == 0

    def test_a_day_with_no_phone_sightings_is_a_zero_row_not_a_missing_one(self, lake):
        _build(lake)

        days = [r for r in _rows(lake, "gold", "daily_rhythm") if r["user_id"] == 1]

        # Spine runs to the data horizon (2026-10-05 local), one row per day from the first.
        assert [r["date_local"] for r in days] == [date(2026, 10, 5)]

    def test_hourly_rates_count_events_per_signal_and_hour(self, lake):
        _bronze(
            lake,
            "household_events",
            [
                {"id": i, "event_type": "info", "subject_type": "user", "subject_id": "1",
                 "verb": "came_online", "message": "m", "source_service": "user",
                 "occurred_at": datetime(2026, 10, 5, 12, i)}
                for i in range(3)
            ],
            "occurred_at",
        )  # fmt: skip

        _build(lake)
        rows = _rows(lake, "gold", "hourly_rates")

        assert rows[0]["signal"] == "info/user/came_online" and rows[0]["n"] == 3
        assert rows[0]["hour_local"] == 8


class TestBuild:
    def test_missing_bronze_tables_skip_their_outputs_instead_of_failing(self, tmp_path):
        _snapshot(tmp_path, "user_types", [{"id": 2, "type": "owner"}])

        counts = _build(tmp_path)

        assert "presence_intervals" not in counts and "sensor_15m" not in counts

    def test_rebuild_is_idempotent_and_writes_a_manifest(self, lake):
        first = _build(lake)
        second = _build(lake)

        assert first == second
        manifest = (lake / "silver" / "_build.json").read_text()
        assert (
            '"presence_gap_minutes": 45' in manifest and '"timezone": "America/Toronto"' in manifest
        )

    def test_no_temp_dirs_are_left_behind(self, lake):
        _build(lake)

        assert not list(lake.glob("*/.tmp-*"))
