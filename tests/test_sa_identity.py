"""Tests for stable sensor identity (sa/identity.py) and the live climate scorer's use of it: a
power-cycled sensor must keep its history, which a smarthome_devices row id cannot promise."""

from datetime import datetime
from unittest.mock import MagicMock

from services.service_sa.sa import identity, shadow

KEY = "athom-tem-hum-sensor-4a4734.local:Temperature"


class FakeCursor:
    """Answers by what the SQL is about; records every statement and its parameters."""

    def __init__(self, current=(), aliased=(), rows=()):
        self.current, self.aliased, self.rows = list(current), list(aliased), list(rows)
        self.executed = []
        self._last = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        self._last = sql

    def fetchall(self):
        sql = self._last or ""
        if "FROM sa_sensor_aliases" in sql:
            return [(i,) for i in self.aliased]
        if "SUBSTRING_INDEX" in sql:
            return [(i,) for i in self.current]
        return self.rows


class TestSensorKey:
    def test_an_esphome_sensor_is_its_host_and_name_never_a_row_id(self):
        key = identity.sensor_key(
            "esphome", "Temperature", esp_entity_id="athom-tem-hum-sensor-4a4734.local:899752953"
        )

        assert key == KEY

    def test_the_key_survives_a_power_cycle_that_changes_the_entity_and_row_ids(self):
        before = identity.sensor_key(
            "esphome", "Temperature", "athom-tem-hum-sensor-4a4734.local:1"
        )
        after = identity.sensor_key("esphome", "Temperature", "athom-tem-hum-sensor-4a4734.local:2")

        assert before == after == KEY

    def test_other_sources_use_their_own_ids_like_silver_does(self):
        assert identity.sensor_key("homeassistant", "x", ha_entity_id="sensor.a") == (
            "homeassistant:sensor.a"
        )
        assert identity.sensor_key("smartthings", "x", st_device_id="abc") == "smartthings:abc"
        assert identity.sensor_key("homeassistant", "Name") == "homeassistant:Name"


class TestHistoryIds:
    def test_current_rows_and_retired_ids_are_both_the_sensors_history(self):
        cursor = FakeCursor(current=[37893], aliased=[37885])

        assert identity.history_ids(cursor, KEY) == [37885, 37893]
        assert all(params == (KEY,) for _sql, params in cursor.executed)  # parameterised

    def test_a_re_adopted_sensor_with_two_current_rows_spans_both(self):
        cursor = FakeCursor(current=[37893, 40001], aliased=[])

        assert identity.history_ids(cursor, KEY) == [37893, 40001]

    def test_an_unknown_sensor_has_no_history(self):
        assert identity.history_ids(FakeCursor(), KEY) == []

    def test_climate_ids_cover_temperature_and_humidity_across_a_power_cycle(self):
        cursor = FakeCursor(
            current=[37893],
            aliased=[37885],
            rows=[
                (37893, "Temperature", "athom-tem-hum-sensor-4a4734.local:899752953"),
                (37897, "Humidity", "athom-tem-hum-sensor-4a4734.local:3577765598"),
            ],
        )
        # the first query (the sensor listing) answers with `rows`; the key lookups with ids
        original = cursor.fetchall
        calls = {"n": 0}

        def fetchall():
            calls["n"] += 1
            return cursor.rows if calls["n"] == 1 else original()

        cursor.fetchall = fetchall

        ids = identity.esphome_climate_ids(cursor)

        assert set(ids) == {"temperature", "humidity"}
        assert ids["temperature"] == [37885, 37893]


class TestLiveClimateUsesStableIdentity:
    def _runner(self, ids):
        runner = shadow.ShadowRunner(MagicMock(), lambda inferences: None)
        runner._connect = lambda: MagicMock()
        runner._scalar_findings = MagicMock(return_value=[])
        return runner

    def _frame(self):
        frame = MagicMock()
        frame.esphome_climate = {"temperature_c": 21.0, "temperature_online": True}
        frame.local_dt = datetime(2026, 11, 19, 8, 0)
        frame.now = datetime(2026, 11, 19, 13, 0)
        return frame

    def test_the_history_query_spans_every_row_id_the_sensor_has_had(self, monkeypatch):
        runner = self._runner(None)
        monkeypatch.setattr(
            shadow.identity, "esphome_climate_ids", lambda cursor: {"temperature": [37885, 37893]}
        )

        runner.climate(self._frame())

        args = runner._scalar_findings.call_args.args
        query, params = args[4], args[5](None)
        assert "smarthome_device_id IN (%s, %s)" in query
        assert params[:2] == (37885, 37893) and len(params) == 3  # the two ids, then `since`

    def test_a_sensor_with_no_known_id_is_skipped_not_guessed(self, monkeypatch):
        runner = self._runner(None)
        monkeypatch.setattr(shadow.identity, "esphome_climate_ids", lambda cursor: {})

        assert runner.climate(self._frame()) == []
        runner._scalar_findings.assert_not_called()
