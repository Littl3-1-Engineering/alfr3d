"""Tests for LF-2b: silver and gold for the contexts LF-0b added (sa/silver_contexts.py).

Each test builds a small synthetic bronze lake and runs the real DuckDB build over it. The
scenarios encode what the real data taught us: Home Assistant describes the *old* house (so its
weather must not be used), a state that has not changed is still held now, midnight-stamped points
are window anchors, and email can arrive dated in the future.
"""

import json
from datetime import date, datetime, timedelta

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import lake, silver, silver_contexts

ETOBICOKE = (43.643972, -79.588917)
NOW = datetime(2026, 10, 10, 12, 0)


def _write(lake_dir, path, rows, day):
    out = lake_dir / path / f"date={day}"
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), out / "part-0.parquet")


def _bronze_by_day(lake_dir, table, rows, ts_field):
    by_day = {}
    for row in rows:
        by_day.setdefault(row[ts_field].date(), []).append(row)
    for day, day_rows in by_day.items():
        _write(lake_dir, f"bronze/{table}", day_rows, day.isoformat())


def _ha(entity, state, changed, updated=None):
    return {
        "entity_id": entity,
        "domain": entity.split(".")[0],
        "state": state,
        "last_changed": changed,
        "last_updated": updated or changed,
    }


def _run(lake_dir, ha_horizon=None, email_horizon=None, **kw):
    if ha_horizon:
        lake.write_horizon(lake_dir / "bronze" / "ha_state_history", ha_horizon)
    if email_horizon:
        lake.write_horizon(lake_dir / "bronze" / "email_messages", email_horizon)
    return silver.build(str(lake_dir), tz="America/Toronto", today=date(2026, 10, 10), **kw)


def _read(lake_dir, layer, table):
    path = lake_dir / layer / table / "part-0.parquet"
    con = duckdb.connect()
    cursor = con.execute(f"SELECT * FROM read_parquet('{path}')")
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _snapshot_environment(lake_dir, lat=ETOBICOKE[0], lon=ETOBICOKE[1]):
    _write(
        lake_dir,
        "bronze/_snapshots/environment",
        [{"id": 1, "name": "home", "latitude": lat, "longitude": lon, "timezone": -14400}],
        "2026-10-10",
    )


class TestSunTimes:
    def test_matches_openweathermaps_own_sunrise_and_sunset_for_etobicoke(self):
        """Verified live on 2026-10-10 against ALFR3D's stored OpenWeatherMap values for the
        household's coordinates: sunrise 07:25 and sunset 18:45 local (EDT, UTC-4), both within a
        minute."""
        sunrise, sunset = silver_contexts.sun_times(date(2026, 10, 9), *ETOBICOKE)

        assert abs((sunrise - datetime(2026, 10, 9, 11, 25)).total_seconds()) < 90
        assert abs((sunset - datetime(2026, 10, 9, 22, 45)).total_seconds()) < 90

    def test_day_length_follows_the_seasons(self):
        for day, expected_hours in ((date(2026, 6, 21), 15.4), (date(2026, 12, 21), 8.9)):
            rise, set_ = silver_contexts.sun_times(day, *ETOBICOKE)
            assert (set_ - rise).total_seconds() / 3600 == pytest.approx(expected_hours, abs=0.2)

    def test_sunset_of_a_western_date_falls_on_the_next_utc_day(self):
        rise, set_ = silver_contexts.sun_times(date(2026, 6, 21), *ETOBICOKE)

        assert set_.date() == date(2026, 6, 22) and rise.date() == date(2026, 6, 21)

    def test_polar_day_and_night_have_no_sunrise(self):
        assert silver_contexts.sun_times(date(2026, 6, 21), 80.0, 0.0) == (None, None)
        assert silver_contexts.sun_times(date(2026, 12, 21), 80.0, 0.0) == (None, None)

    def test_the_same_day_in_serbia_is_a_different_sun(self):
        """The reason this matters: Home Assistant's home is Novi Sad, 6.6 hours of longitude east
        of Toronto, so every one of its sun and weather entities is for the wrong place."""
        toronto, _ = silver_contexts.sun_times(date(2026, 10, 9), *ETOBICOKE)
        novi_sad, _ = silver_contexts.sun_times(date(2026, 10, 9), 45.237, 19.810)

        assert (toronto - novi_sad).total_seconds() / 3600 == pytest.approx(6.6, abs=0.4)


class TestDayContextSun:
    def test_day_context_carries_sunrise_sunset_and_daylight_when_the_location_is_known(self):
        rows = silver.day_context_rows(date(2026, 10, 9), date(2026, 10, 10), ETOBICOKE)

        assert rows[0]["sunrise_utc"] is not None and rows[0]["daylight_minutes"] > 600

    def test_without_a_location_the_sun_columns_are_empty_not_invented(self):
        (row,) = silver.day_context_rows(date(2026, 10, 9), date(2026, 10, 9))

        assert row["sunrise_utc"] is None and row["daylight_minutes"] is None

    def test_the_built_table_has_local_sun_times_from_the_environment_snapshot(self, tmp_path):
        _snapshot_environment(tmp_path)
        _bronze_by_day(
            tmp_path,
            "household_events",
            [
                {
                    "id": 1, "event_type": "info", "subject_type": "u", "subject_id": "1",
                    "verb": "x", "message": "m", "source_service": "s",
                    "occurred_at": datetime(2026, 10, 9, 12, 0),
                }
            ],
            "occurred_at",
        )  # fmt: skip

        _run(tmp_path)
        day = [
            r for r in _read(tmp_path, "silver", "day_context") if r["date"] == date(2026, 10, 9)
        ][0]

        assert day["sunrise_local"].hour == 7 and day["sunset_local"].hour == 18


class TestHaSilver:
    def _lake(self, tmp_path):
        rows = [
            # A temperature that changes through the day
            _ha("sensor.t", "10", datetime(2026, 10, 10, 0, 0)),  # midnight anchor
            _ha("sensor.t", "20", datetime(2026, 10, 10, 0, 15)),
            # A media player that never changes (only anchors on two days)
            _ha("media_player.tv", "off", datetime(2026, 10, 9, 0, 0)),
            _ha("media_player.tv", "off", datetime(2026, 10, 10, 0, 0)),
            _ha("media_player.tv", "playing", datetime(2026, 10, 10, 1, 30)),
            # Unavailable for most of its life
            _ha("media_player.speaker", "unavailable", datetime(2026, 10, 9, 0, 0)),
            _ha("media_player.speaker", "unavailable", datetime(2026, 10, 10, 0, 0)),
            # A sensor that is just a timestamp string
            _ha(
                "sensor.sun_next_rising", "2026-10-10T11:26:00+00:00", datetime(2026, 10, 9, 20, 0)
            ),
        ]
        _bronze_by_day(tmp_path, "ha_state_history", rows, "last_changed")
        return _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 6, 0))

    def test_midnight_anchors_are_flagged_but_kept(self, tmp_path):
        self._lake(tmp_path)

        states = {
            (r["entity_id"], r["changed_utc"]): r for r in _read(tmp_path, "silver", "ha_states")
        }

        assert states[("sensor.t", datetime(2026, 10, 10, 0, 0))]["is_anchor"] is True
        assert states[("sensor.t", datetime(2026, 10, 10, 0, 15))]["is_anchor"] is False

    def test_a_state_is_held_until_the_next_change_and_the_last_until_the_export_horizon(
        self, tmp_path
    ):
        self._lake(tmp_path)

        tv = [
            r
            for r in _read(tmp_path, "silver", "ha_intervals")
            if r["entity_id"] == "media_player.tv"
        ]

        # off from the 9th, merged across the midnight anchor, until it started playing at 01:30;
        # playing until the horizon, 06:00. No second "off" interval for the anchor.
        assert [(r["state"], r["start_utc"], r["end_utc"]) for r in tv] == [
            ("off", datetime(2026, 10, 9, 0, 0), datetime(2026, 10, 10, 1, 30)),
            ("playing", datetime(2026, 10, 10, 1, 30), datetime(2026, 10, 10, 6, 0)),
        ]
        assert tv[0]["n_points"] == 2 and tv[0]["has_real_change"] is False

    def test_unavailable_is_a_flag_not_a_value(self, tmp_path):
        self._lake(tmp_path)

        (speaker,) = [
            r
            for r in _read(tmp_path, "silver", "ha_intervals")
            if r["entity_id"] == "media_player.speaker"
        ]

        assert speaker["is_unavailable"] is True and speaker["value"] is None

    def test_entities_are_classified_by_what_they_actually_hold(self, tmp_path):
        self._lake(tmp_path)

        kinds = {r["entity_id"]: r["kind"] for r in _read(tmp_path, "silver", "ha_entities")}

        assert kinds == {
            "sensor.t": "numeric",
            "media_player.tv": "categorical",
            "media_player.speaker": "unavailable",
            "sensor.sun_next_rising": "metadata",
        }

    def test_scalar_hourly_is_time_weighted_and_reports_how_much_of_the_hour_it_covers(
        self, tmp_path
    ):
        self._lake(tmp_path)

        hours = {
            r["bucket_utc"]: r
            for r in _read(tmp_path, "gold", "scalar_hourly")
            if r["series_key"] == "ha:sensor.t"
        }

        # 10 for the first 15 minutes of 00:00, then 20 for the remaining 45: (10*15 + 20*45) / 60.
        first = hours[datetime(2026, 10, 10, 0, 0)]
        assert first["mean"] == pytest.approx(17.5) and first["min"] == 10 and first["max"] == 20
        assert first["coverage"] == pytest.approx(1.0)
        # Held at 20 until the 06:00 horizon, so the hours in between are fully covered...
        assert hours[datetime(2026, 10, 10, 3, 0)]["mean"] == 20
        # ...and the series does not extend past what was observed.
        assert datetime(2026, 10, 10, 7, 0) not in hours

    def test_a_partial_hour_has_partial_coverage(self, tmp_path):
        rows = [_ha("sensor.t", "5", datetime(2026, 10, 10, 2, 30))]
        _bronze_by_day(tmp_path, "ha_state_history", rows, "last_changed")
        _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 2, 45))

        (hour,) = [
            r for r in _read(tmp_path, "gold", "scalar_hourly") if r["series_key"] == "ha:sensor.t"
        ]

        assert hour["coverage"] == pytest.approx(0.25) and hour["mean"] == 5

    def test_state_hourly_splits_an_hour_between_states(self, tmp_path):
        self._lake(tmp_path)

        tv = {
            (r["bucket_utc"], r["state"]): r["minutes"]
            for r in _read(tmp_path, "gold", "state_hourly")
            if r["series_key"] == "ha:media_player.tv"
        }

        assert tv[(datetime(2026, 10, 10, 1, 0), "off")] == pytest.approx(30)
        assert tv[(datetime(2026, 10, 10, 1, 0), "playing")] == pytest.approx(30)
        assert tv[(datetime(2026, 10, 10, 3, 0), "playing")] == pytest.approx(60)

    def test_entities_that_describe_the_old_house_are_flagged_with_the_distance(self, tmp_path):
        rows = [
            _ha("sensor.openweathermap_temperature", "15.9", datetime(2026, 10, 10, 0, 30)),
            _ha("sensor.littl3zen_battery_level", "80", datetime(2026, 10, 10, 0, 30)),
        ]
        _bronze_by_day(tmp_path, "ha_state_history", rows, "last_changed")
        config = {
            "current": {
                "latitude": 45.2370881,
                "longitude": 19.81,
                "time_zone": "Europe/Belgrade",
                "location_name": "Cassiopeia",
            },
            "history": [],
        }
        (tmp_path / "bronze" / "ha_state_history" / "_ha_config.json").write_text(
            json.dumps(config)
        )
        _snapshot_environment(tmp_path)
        _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 2, 0))

        entities = {r["entity_id"]: r for r in _read(tmp_path, "silver", "ha_entities")}

        weather = entities["sensor.openweathermap_temperature"]
        assert weather["describes_ha_home"] is True
        assert weather["ha_home_distance_km"] == pytest.approx(7400, rel=0.05)  # Novi Sad - Toronto
        assert entities["sensor.littl3zen_battery_level"]["describes_ha_home"] is False

    def test_an_unknown_ha_home_leaves_the_distance_empty_rather_than_guessing(self, tmp_path):
        _bronze_by_day(
            tmp_path,
            "ha_state_history",
            [_ha("sensor.t", "1", datetime(2026, 10, 10, 1, 0))],
            "last_changed",
        )
        _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 2, 0))

        (row,) = _read(tmp_path, "silver", "ha_entities")

        assert row["ha_home_distance_km"] is None


class TestWeather:
    def _env(self, recorded, temp, humidity=50, description="clear sky"):
        return {
            "id": int(recorded.timestamp()), "environment_id": 1, "kind": "weather",
            "recorded_at": recorded, "temperature": temp, "humidity": humidity, "pressure": 1015,
            "wind": 10.0, "wind_dir": "NW", "description": description, "low": 8, "high": 21,
            "sunrise": None, "sunset": None,
        }  # fmt: skip

    def test_weather_comes_from_alfr3ds_toronto_record_never_from_home_assistant(self, tmp_path):
        """At the same moment Home Assistant reported 15.9 C / 62 % (Novi Sad) and ALFR3D recorded
        19.9 C / 40 % (Etobicoke). The household's context must be the latter."""
        _bronze_by_day(
            tmp_path,
            "environment_history",
            [self._env(datetime(2026, 10, 9, 20, 26), 19.9, 40)],
            "recorded_at",
        )
        ha = [_ha("sensor.openweathermap_temperature", "15.9", datetime(2026, 10, 9, 20, 0))]
        _bronze_by_day(tmp_path, "ha_state_history", ha, "last_changed")
        _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 2, 0))

        rows = _read(tmp_path, "silver", "weather_hourly")

        assert {r["temperature_c"] for r in rows} == {19.9}  # never Home Assistant's 15.9
        assert {r["humidity_pct"] for r in rows} == {40}
        assert {r["source"] for r in rows} == {"environment_history"}
        assert rows[0]["bucket_utc"] == datetime(2026, 10, 9, 20, 0)

    def test_weather_is_never_carried_past_the_lake_horizon(self, tmp_path):
        """Hours that have not happened yet must not receive an observation."""
        _bronze_by_day(
            tmp_path,
            "environment_history",
            [self._env(datetime(2026, 10, 9, 20, 26), 19.9)],
            "recorded_at",
        )
        history = [
            {"device_id": 1, "name": "d", "timestamp": datetime(2026, 10, 9, 22, 30),
             "last_online": datetime(2026, 10, 9, 22, 29), "device_type": 2, "user_id": 2}
        ]  # fmt: skip
        _bronze_by_day(tmp_path, "device_history", history, "timestamp")
        _run(tmp_path)

        last = max(r["bucket_utc"] for r in _read(tmp_path, "silver", "weather_hourly"))

        assert last == datetime(2026, 10, 9, 22, 0)  # the horizon is 22:30, not 20:26 + 6 h

    def test_a_reading_is_carried_forward_but_not_for_ever(self, tmp_path):
        _bronze_by_day(
            tmp_path,
            "environment_history",
            [
                self._env(datetime(2026, 10, 10, 0, 10), 12.0),
                self._env(datetime(2026, 10, 10, 10, 10), 18.0),
            ],
            "recorded_at",
        )
        _run(tmp_path)

        hours = {
            r["bucket_utc"].hour: r["temperature_c"]
            for r in _read(tmp_path, "silver", "weather_hourly")
        }

        assert hours[0] == 12.0 and hours[5] == 12.0  # carried up to six hours
        assert 8 not in hours and 6 not in hours  # then left empty, not stretched across the gap
        assert hours[10] == 18.0

    def test_forecast_rows_are_not_mistaken_for_observations(self, tmp_path):
        forecast = self._env(datetime(2026, 10, 10, 1, 0), 99.0)
        forecast["kind"] = "forecast"
        _bronze_by_day(
            tmp_path,
            "environment_history",
            [self._env(datetime(2026, 10, 10, 0, 0), 11.0), forecast],
            "recorded_at",
        )
        _run(tmp_path)

        temps = {r["temperature_c"] for r in _read(tmp_path, "silver", "weather_hourly")}

        assert temps == {11.0}


class TestEmail:
    def _msg(
        self, mid, received, labels="INBOX,CATEGORY_PROMOTIONS", sender="a@shop.com", unread=False
    ):
        return {
            "message_id": mid, "thread_id": "t" + mid, "received_utc": received,
            "sender_name": "Shop", "sender_email": sender, "sender_domain": sender.split("@")[1],
            "subject": "Sale", "labels": labels, "is_unread": unread, "size_estimate": 100,
        }  # fmt: skip

    def test_email_events_have_local_time_and_a_gmail_category(self, tmp_path):
        msgs = [
            self._msg("m1", datetime(2026, 10, 9, 13, 30)),
            self._msg("m2", datetime(2026, 10, 9, 14, 0), labels="INBOX,CATEGORY_UPDATES"),
            self._msg("m3", datetime(2026, 10, 9, 15, 0), labels="SENT"),
        ]
        _bronze_by_day(tmp_path, "email_messages", msgs, "received_utc")
        _run(tmp_path, email_horizon=datetime(2026, 10, 10, 0, 0))

        rows = {r["message_id"]: r for r in _read(tmp_path, "silver", "email_events")}

        assert rows["m1"]["received_local"] == datetime(2026, 10, 9, 9, 30)
        assert [rows[m]["category"] for m in ("m1", "m2", "m3")] == [
            "promotions",
            "updates",
            "uncategorised",
        ]
        assert rows["m3"]["in_inbox"] is False

    def test_email_hourly_is_zero_filled_through_the_export_horizon(self, tmp_path):
        msgs = [
            self._msg("m1", datetime(2026, 10, 9, 13, 30)),
            self._msg("m2", datetime(2026, 10, 9, 13, 45), unread=True),
        ]
        _bronze_by_day(tmp_path, "email_messages", msgs, "received_utc")
        _run(tmp_path, email_horizon=datetime(2026, 10, 9, 17, 30))

        hours = {r["bucket_utc"]: r for r in _read(tmp_path, "gold", "email_hourly")}

        assert (
            hours[datetime(2026, 10, 9, 13, 0)]["n"] == 2
            and hours[datetime(2026, 10, 9, 13, 0)]["n_unread"] == 1
        )
        assert hours[datetime(2026, 10, 9, 13, 0)]["n_promotions"] == 2
        # Quiet hours are rows with n = 0, not missing rows: a rate learner needs the zeros.
        assert hours[datetime(2026, 10, 9, 15, 0)]["n"] == 0
        assert max(hours) == datetime(2026, 10, 9, 17, 0)

    def test_email_hourly_stops_at_the_horizon_not_at_the_last_message(self, tmp_path):
        _bronze_by_day(
            tmp_path,
            "email_messages",
            [self._msg("m1", datetime(2026, 10, 9, 13, 30))],
            "received_utc",
        )
        _run(tmp_path, email_horizon=datetime(2026, 10, 9, 20, 0))

        assert max(r["bucket_utc"] for r in _read(tmp_path, "gold", "email_hourly")) == datetime(
            2026, 10, 9, 20, 0
        )

    def test_sender_daily_counts_email_and_phone_notifications(self, tmp_path):
        msgs = [self._msg(f"m{i}", datetime(2026, 10, 9, 13, i)) for i in range(3)]
        _bronze_by_day(tmp_path, "email_messages", msgs, "received_utc")
        events = [
            {
                "id": i,
                "event_type": "notification",
                "subject_type": "sender",
                "subject_id": "Alice",
                "verb": "messaged",
                "message": "m",
                "source_service": "api",
                "occurred_at": datetime(2026, 10, 9, 14, i),
            }
            for i in range(2)
        ]
        _bronze_by_day(tmp_path, "household_events", events, "occurred_at")
        _run(tmp_path, email_horizon=datetime(2026, 10, 10, 0, 0))

        rows = {(r["source"], r["sender"]): r["n"] for r in _read(tmp_path, "gold", "sender_daily")}

        assert rows == {("gmail", "a@shop.com"): 3, ("notification:messaged", "Alice"): 2}


class TestContextHourly:
    def test_one_row_per_hour_with_time_daylight_weather_calendar_and_who_is_home(self, tmp_path):
        _snapshot_environment(tmp_path)
        _write(tmp_path, "bronze/_snapshots/user_types", [{"id": 2, "type": "owner"}], "2026-10-10")
        _write(
            tmp_path,
            "bronze/_snapshots/user",
            [{"id": 1, "username": "athos", "type": 2}],
            "2026-10-10",
        )
        # A phone seen 08:00-10:00 local (12:00-14:00 UTC) on a Friday, plenty of collector rows.
        history = []
        for minute in range(0, 24 * 60, 5):
            t = datetime(2026, 10, 9, 0, 0) + timedelta(minutes=minute)
            history.append(
                {
                    "device_id": 9,
                    "name": "d",
                    "timestamp": t + timedelta(minutes=1),
                    "last_online": t,
                    "device_type": 2,
                    "user_id": 2,
                }
            )
        for minute in range(0, 120):
            t = datetime(2026, 10, 9, 12, 0) + timedelta(minutes=minute)
            history.append(
                {
                    "device_id": 1,
                    "name": "p",
                    "timestamp": t + timedelta(minutes=1),
                    "last_online": t,
                    "device_type": 5,
                    "user_id": 1,
                }
            )
        _bronze_by_day(tmp_path, "device_history", history, "timestamp")
        calendar = {
            "title": "x",
            "notes": None,
            "address": None,
            "conference_uri": None,
            "start_time": datetime(2026, 10, 9, 13, 30),
            "end_time": datetime(2026, 10, 9, 14, 30),
        }
        _bronze_by_day(tmp_path, "calendar_events", [calendar], "start_time")
        weather = {
            "id": 1,
            "environment_id": 1,
            "kind": "weather",
            "recorded_at": datetime(2026, 10, 9, 11, 40),
            "temperature": 18.0,
            "humidity": 55,
            "pressure": 1016,
            "wind": 5.0,
            "wind_dir": "N",
            "description": "scattered clouds",
            "low": 9,
            "high": 20,
            "sunrise": None,
            "sunset": None,
        }
        _bronze_by_day(tmp_path, "environment_history", [weather], "recorded_at")
        _run(tmp_path)

        hours = {r["bucket_utc"]: r for r in _read(tmp_path, "gold", "context_hourly")}
        morning = hours[datetime(2026, 10, 9, 12, 0)]  # 08:00 local, Friday

        assert (
            morning["hour_local"] == 8
            and morning["dow_local"] == 4
            and morning["season"] == "autumn"
        )
        assert (
            morning["is_daylight"] is True
            and hours[datetime(2026, 10, 9, 23, 0)]["is_daylight"]
            is False  # 19:00 local, after sunset
        )
        assert (
            morning["people_home"] == 1 and hours[datetime(2026, 10, 9, 18, 0)]["people_home"] == 0
        )
        assert (
            morning["outdoor_temp_c"] == 18.0 and morning["outdoor_condition"] == "scattered clouds"
        )
        assert hours[datetime(2026, 10, 9, 13, 0)]["calendar_busy_minutes"] == pytest.approx(30)
        assert hours[datetime(2026, 10, 9, 14, 0)]["calendar_busy_minutes"] == pytest.approx(30)
        assert hours[datetime(2026, 10, 9, 18, 0)]["calendar_busy_minutes"] == 0


class TestDeck:
    DEV = "39bef6ad-a5c8-475d-93a5-36af71a8b8ac"

    def _row(self, minutes, *, device=DEV, source="device_snapshot", heartbeat=0, **state):
        base = {
            "battery_bucket": None, "is_charging": None, "dnd_active": None,
            "headset_connected": None, "network_type": None, "network_quality": None,
            "orientation": None, "active_surface": None, "top_app": None,
            "terminal_session_active": None, "relay_enabled": None,
        }  # fmt: skip
        base.update(state)
        return {
            "id": minutes + 1, "source": source, "device_install_id": device,
            "observed_at": datetime(2026, 10, 10, 8, 0) + timedelta(minutes=minutes),
            "is_heartbeat": heartbeat, **base,
        }  # fmt: skip

    def _lake(self, tmp_path, rows):
        _bronze_by_day(tmp_path, "deck_context_history", rows, "observed_at")
        return _run(tmp_path)

    def test_identical_reports_merge_into_one_held_interval(self, tmp_path):
        rows = [
            self._row(0, dnd_active=0, battery_bucket=60),
            self._row(30, dnd_active=0, battery_bucket=60, heartbeat=1),
            self._row(60, dnd_active=1, battery_bucket=60),
        ]
        self._lake(tmp_path, rows)

        runs = _read(tmp_path, "silver", "deck_intervals")

        assert [
            (r["dnd_active"], r["start_utc"].minute + 60 * (r["start_utc"].hour - 8)) for r in runs
        ] == [(0, 0), (1, 60)]
        assert runs[0]["n_reports"] == 2 and runs[0]["n_heartbeats"] == 1
        # held until the next different report, not past it
        assert runs[0]["end_utc"] == datetime(2026, 10, 10, 9, 0)

    def test_a_deck_that_goes_quiet_is_not_assumed_to_hold_its_state(self, tmp_path):
        self._lake(tmp_path, [self._row(0, dnd_active=1)])

        (run,) = _read(tmp_path, "silver", "deck_intervals")

        assert run["end_utc"] - run["start_utc"] == timedelta(
            minutes=silver_contexts.DECK_SILENCE_MINUTES
        )

    def test_two_decks_and_the_surface_report_are_separate_streams(self, tmp_path):
        other = "f05e8522-927c-4758-a424-5ac0dda165e2"
        rows = [
            self._row(0, dnd_active=1),
            self._row(1, device=other, dnd_active=0),
            self._row(2, device=None, source="surface_state", active_surface="music"),
        ]
        self._lake(tmp_path, rows)

        runs = _read(tmp_path, "silver", "deck_intervals")

        assert len(runs) == 3

    def test_unknown_facets_stay_unknown_in_the_hourly_series(self, tmp_path):
        rows = [self._row(0, dnd_active=1), self._row(30, dnd_active=0)]
        self._lake(tmp_path, rows)

        series = {r["series_key"] for r in _read(tmp_path, "gold", "state_hourly")}

        assert "deck:39bef6ad:dnd_active" in series
        assert "deck:39bef6ad:is_charging" not in series  # never reported: no row at all

    def test_state_hourly_splits_the_hour_between_dnd_on_and_off(self, tmp_path):
        rows = [
            self._row(0, dnd_active=1),
            self._row(30, dnd_active=0),
            self._row(59, dnd_active=0),
        ]
        self._lake(tmp_path, rows)

        hour = {
            r["state"]: r["minutes"]
            for r in _read(tmp_path, "gold", "state_hourly")
            if r["series_key"] == "deck:39bef6ad:dnd_active"
            and r["bucket_utc"] == datetime(2026, 10, 10, 8, 0)
        }

        assert hour["1"] == pytest.approx(30) and hour["0"] == pytest.approx(30)

    def test_battery_is_a_scalar_series_at_the_bucket_midpoint(self, tmp_path):
        rows = [self._row(0, battery_bucket=60), self._row(30, battery_bucket=55)]
        self._lake(tmp_path, rows)

        (hour,) = [
            r for r in _read(tmp_path, "gold", "scalar_hourly")
            if r["series_key"] == "deck:39bef6ad:battery"
            and r["bucket_utc"] == datetime(2026, 10, 10, 8, 0)
        ]  # fmt: skip

        assert hour["mean"] == pytest.approx((62.5 * 30 + 57.5 * 30) / 60)
        assert hour["source"] == "deck"

    def test_no_deck_data_builds_nothing(self, tmp_path):
        counts = _run(tmp_path)

        assert "deck_intervals" not in counts


class TestBuild:
    def test_a_lake_with_none_of_the_new_sources_still_builds(self, tmp_path):
        counts = _run(tmp_path)

        assert (
            "ha_states" not in counts
            and "email_events" not in counts
            and "context_hourly" not in counts
        )

    def test_rebuilding_is_idempotent(self, tmp_path):
        _bronze_by_day(
            tmp_path,
            "ha_state_history",
            [_ha("sensor.t", "1", datetime(2026, 10, 10, 1, 0))],
            "last_changed",
        )
        first = _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 5, 0))

        assert _run(tmp_path, ha_horizon=datetime(2026, 10, 10, 5, 0)) == first


class TestHorizon:
    def test_the_horizon_round_trips_and_a_missing_one_is_none(self, tmp_path):
        assert lake.read_horizon(tmp_path / "nothing") is None
        lake.write_horizon(tmp_path / "t", datetime(2026, 10, 10, 4, 48, 3, 999))

        assert lake.read_horizon(tmp_path / "t") == datetime(2026, 10, 10, 4, 48, 3)

    def test_a_corrupt_horizon_file_is_treated_as_missing(self, tmp_path):
        (tmp_path / "t").mkdir()
        (tmp_path / "t" / lake.HORIZON_FILE).write_text("not a date")

        assert lake.read_horizon(tmp_path / "t") is None
