"""Tests for the context registry (sa/context_registry.py): `context_hourly` generated from the
registry equals the hand-written SQL it replaced, a new feature is one registration, privacy scope
is enforced, and the declarations are sound.

The reference is the ORIGINAL hand-written `context_hourly` query, copied verbatim below, run over
the same synthetic tables as the registry-generated one, in every combination of optional sources.
"""

from dataclasses import replace
from datetime import datetime, timedelta

import duckdb
import pytest

from services.service_sa.sa import context_registry as reg
from services.service_sa.sa import silver


def _legacy_context_hourly(has_weather, has_calendar):
    """The hand-written query as it was before the registry (silver_contexts.build_gold)."""
    weather_cols = (
        "w.temperature_c AS outdoor_temp_c, w.humidity_pct AS outdoor_humidity_pct, "
        "w.pressure_hpa AS outdoor_pressure_hpa, w.description AS outdoor_condition"
        if has_weather
        else "NULL::DOUBLE AS outdoor_temp_c, NULL::DOUBLE AS outdoor_humidity_pct, "
        "NULL::DOUBLE AS outdoor_pressure_hpa, NULL::VARCHAR AS outdoor_condition"
    )
    return f"""
            WITH people AS (
              SELECT bucket_utc, BOOL_OR(observed) AS observed,
                     SUM((minutes_home >= 30)::INT) AS people_home
              FROM g_presence_grid GROUP BY bucket_utc),
            spine AS (
              SELECT UNNEST(generate_series(MIN(bucket_utc), MAX(bucket_utc), INTERVAL 1 HOUR))
                       AS bucket_utc
              FROM people)
            SELECT s.bucket_utc, to_local(s.bucket_utc) AS bucket_local,
                   CAST(to_local(s.bucket_utc) AS DATE) AS date_local,
                   hour(to_local(s.bucket_utc)) AS hour_local, d.dow AS dow_local,
                   d.is_weekend, d.is_holiday, d.holiday_name, d.month, d.season,
                   CASE WHEN d.sunrise_utc IS NOT NULL
                        THEN (s.bucket_utc + INTERVAL 30 MINUTE)
                             BETWEEN d.sunrise_utc AND d.sunset_utc
                   END AS is_daylight,
                   {weather_cols},
                   {"COALESCE(c.busy_minutes, 0)" if has_calendar else "NULL::DOUBLE"}
                     AS calendar_busy_minutes,
                   CASE WHEN p.observed THEN p.people_home END AS people_home
            FROM spine s
            LEFT JOIN s_day_context d ON d.date = CAST(to_local(s.bucket_utc) AS DATE)
            {"LEFT JOIN s_weather_hourly w ON w.bucket_utc = s.bucket_utc" if has_weather else ""}
            {"LEFT JOIN calendar_hourly c ON c.bucket_utc = s.bucket_utc" if has_calendar else ""}
            LEFT JOIN people p ON p.bucket_utc = s.bucket_utc
            ORDER BY s.bucket_utc"""


START = datetime(2026, 10, 5, 0)  # a Monday, UTC
HOURS = 24 * 12  # 12 days, spanning a weekend and (with the October dates) Thanksgiving


def _con(with_weather=True, with_calendar=True, captured_from=None):
    con = duckdb.connect()
    con.execute(f"CREATE MACRO to_local(ts) AS timezone('{silver.TIMEZONE}', timezone('UTC', ts))")
    # The presence grid: two people, the second absent some hours, some hours unobserved.
    rows = []
    for i in range(HOURS):
        t = START + timedelta(hours=i)
        observed = i % 29 != 0
        rows.append((t, 1, 60.0 if i % 24 < 9 else 0.0, observed))
        rows.append((t, 2, 60.0 if i % 5 else 10.0, observed))
    con.execute(
        "CREATE TABLE g_presence_grid (bucket_utc TIMESTAMP, user_id INT, minutes_home DOUBLE, "
        "observed BOOLEAN)"
    )
    con.executemany("INSERT INTO g_presence_grid VALUES (?, ?, ?, ?)", rows)
    days = silver.day_context_rows(
        START.date() - timedelta(days=1), START.date() + timedelta(days=14), (43.65, -79.57)
    )
    import pyarrow as pa

    con.register("dc", pa.Table.from_pylist(days, schema=silver.DAY_CONTEXT_SCHEMA))
    con.execute("CREATE TABLE s_day_context AS SELECT * FROM dc")
    if with_weather:
        con.execute(
            "CREATE TABLE s_weather_hourly (bucket_utc TIMESTAMP, temperature_c DOUBLE, "
            "humidity_pct DOUBLE, pressure_hpa DOUBLE, description VARCHAR, "
            "forecast_temp_c DOUBLE, forecast_rain_probability DOUBLE)"
        )
        con.executemany(
            "INSERT INTO s_weather_hourly VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    START + timedelta(hours=i),
                    10.0 + (i % 17) / 2,
                    40.0 + i % 30,
                    1000.0 + i % 9,
                    "light rain" if i % 7 == 0 else "clear sky",
                    9.0 + (i % 13) / 3,
                    (i % 10) / 10.0,
                )
                for i in range(HOURS)
                if i % 11 != 0  # gaps: a missing hour is a NULL, not a zero
            ],
        )
    if with_calendar:
        con.execute("CREATE TABLE calendar_hourly (bucket_utc TIMESTAMP, busy_minutes DOUBLE)")
        con.executemany(
            "INSERT INTO calendar_hourly VALUES (?, ?)",
            [(START + timedelta(hours=i * 13), 30.0 + i) for i in range(20)],
        )
        # the calendar was captured from the first hour of the window unless a test says otherwise
        con.execute("CREATE TABLE calendar_capture (captured_from TIMESTAMP)")
        con.execute("INSERT INTO calendar_capture VALUES (?)", [captured_from or START])
    return con


def _available(con, forecast=False):
    tables = {
        r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    } | {"g_presence_grid"}
    # the build adds this token when weather_hourly carries the forecast columns
    return tables | ({"s_weather_forecast"} if forecast else set())


def _registry_table(con):
    query = reg.features_query(_available(con))
    con.execute(f"CREATE TABLE context_features AS {query}")
    con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")
    return reg.context_hourly_query(_available(con))


class TestContextHourlyIsUnchanged:
    @pytest.mark.parametrize(
        "weather,calendar", [(True, True), (True, False), (False, True), (False, False)]
    )
    def test_the_registry_table_equals_the_hand_written_one(self, weather, calendar):
        con = _con(weather, calendar)
        legacy = _legacy_context_hourly(weather, calendar)
        new = _registry_table(con)

        old_cols = [d[0] for d in con.execute(f"SELECT * FROM ({legacy}) LIMIT 0").description]
        new_cols = [d[0] for d in con.execute(f"SELECT * FROM ({new}) LIMIT 0").description]
        only_old = con.execute(f"SELECT * FROM ({legacy}) EXCEPT SELECT * FROM ({new})").fetchall()
        only_new = con.execute(f"SELECT * FROM ({new}) EXCEPT SELECT * FROM ({legacy})").fetchall()
        rows = con.execute(f"SELECT COUNT(*) FROM ({new})").fetchone()[0]

        assert new_cols == old_cols  # same names, same order
        assert only_old == [] and only_new == []  # same values, every row
        assert rows == HOURS

    def test_a_typed_null_stands_in_for_a_source_that_does_not_exist(self):
        con = _con(with_weather=False, with_calendar=False)
        new = _registry_table(con)

        row = con.execute(
            f"SELECT outdoor_temp_c, outdoor_condition, calendar_busy_minutes FROM ({new}) LIMIT 1"
        ).fetchone()

        assert row == (None, None, None)


class TestOneRegistrationAddsAFeature:
    def _with_extra(self, **kw):
        extra = reg.Feature(
            "throwaway_feature",
            "float",
            "p.people_home * 2.0",
            ("people",),
            provenance="a test",
            **kw,
        )
        return reg.REGISTRY + (extra,)

    def test_a_new_feature_reaches_both_tables_with_no_other_edit(self):
        con = _con()
        features = self._with_extra()
        query = reg.features_query(_available(con), features)
        con.execute(f"CREATE TABLE context_features AS {query}")
        con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")

        wide = reg.context_hourly_query(_available(con), features)
        long_n = con.execute(
            "SELECT COUNT(*) FROM context_features WHERE feature_key = 'throwaway_feature'"
        ).fetchone()[0]
        mismatches = con.execute(
            f"SELECT COUNT(*) FROM ({wide}) WHERE people_home IS NOT NULL "
            "AND throwaway_feature IS DISTINCT FROM people_home * 2.0"
        ).fetchone()[0]

        assert long_n > 0
        assert mismatches == 0

    def test_the_existing_columns_do_not_move_when_a_feature_is_added(self):
        con = _con()
        base = _registry_table(con)
        features = self._with_extra()
        wide = reg.context_hourly_query(_available(con), features)

        base_cols = [d[0] for d in con.execute(f"SELECT * FROM ({base}) LIMIT 0").description]
        new_cols = [d[0] for d in con.execute(f"SELECT * FROM ({wide}) LIMIT 0").description]

        assert new_cols[: len(base_cols)] == base_cols
        assert new_cols[-1] == "throwaway_feature"

    def test_a_feature_kept_out_of_the_wide_table_is_still_in_the_long_one(self):
        con = _con()
        features = self._with_extra(in_context_hourly=False)
        con.execute(
            f"CREATE TABLE context_features AS {reg.features_query(_available(con), features)}"
        )
        con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")

        wide = reg.context_hourly_query(_available(con), features)
        cols = [d[0] for d in con.execute(f"SELECT * FROM ({wide}) LIMIT 0").description]

        assert "throwaway_feature" not in cols
        assert (
            con.execute(
                "SELECT COUNT(*) FROM context_features WHERE feature_key = 'throwaway_feature'"
            ).fetchone()[0]
            > 0
        )


class TestPrivacyScope:
    def test_a_restricted_feature_is_registered_but_never_exposed(self):
        keys = reg.learner_candidates()["features"]

        assert "precise_location" in {f.key for f in reg.REGISTRY}
        assert "precise_location" not in keys

    def test_even_asking_for_it_does_not_expose_a_restricted_feature(self):
        keys = reg.learner_candidates(opened={"precise_location"})["features"]

        assert "precise_location" not in keys

    def test_an_owner_opened_feature_is_exposed_only_once_opened(self):
        opened_feature = reg.Feature(
            "coarse_location", "text", "p.people_home", ("people",), privacy=reg.OWNER_OPENED
        )
        features = reg.REGISTRY + (opened_feature,)

        assert "coarse_location" not in reg.learner_candidates(features=features)["features"]
        assert (
            "coarse_location" in reg.learner_candidates({"coarse_location"}, features)["features"]
        )

    def test_a_restricted_feature_is_never_built_into_the_lake(self):
        con = _con()
        sneaky = reg.Feature(
            "sneaky", "float", "p.people_home", ("people",), privacy=reg.RESTRICTED
        )

        query = reg.features_query(_available(con), reg.REGISTRY + (sneaky,))

        assert "sneaky" not in query
        assert not reg.buildable(sneaky, _available(con))

    def test_validation_rejects_a_restricted_feature_that_is_built(self):
        bad = reg.Feature("bad", "float", "p.people_home", ("people",), privacy=reg.RESTRICTED)

        problems = reg.validate(reg.REGISTRY + (bad,))

        assert any("restricted" in p for p in problems)


class TestRegistryIsSound:
    def test_the_shipped_registry_has_no_problems(self):
        assert reg.validate() == []

    def test_duplicate_keys_unknown_kinds_and_unknown_joins_are_caught(self):
        dup = replace(reg.REGISTRY[0])
        odd = reg.Feature("odd", "complex", "x.y", ("nowhere",))

        problems = reg.validate(reg.REGISTRY + (dup, odd))

        assert any("duplicate feature key" in p for p in problems)
        assert any("unknown kind" in p for p in problems)
        assert any("unknown join" in p for p in problems)

    def test_context_hourly_columns_are_the_registered_features_in_order(self):
        con = _con()
        cols = [
            d[0] for d in con.execute(f"SELECT * FROM ({_registry_table(con)}) LIMIT 0").description
        ]
        expected = [f.key for f in reg.REGISTRY if f.in_context_hourly]

        assert cols[5:] == expected

    def test_every_named_reader_is_a_real_learner_or_card_or_observer(self):
        import pkgutil

        from services.service_sa.sa import learners

        known = {
            "calendar_observer",
            "deck_observer",
            "scalar_baseline",
            "drift",
            "presence_profile",
            "daytime_profile",
            "household_day",
            "stay_profile",
            "event_rate",
            "device_rhythm",
        }
        modules = {m.name for m in pkgutil.iter_modules(learners.__path__)}
        readers = {r for f in reg.REGISTRY for r in f.readers} | {
            r for s in reg.SERIES_FAMILIES for r in s.readers
        }

        assert readers <= known
        assert {"scalar", "drift", "presence", "daytime", "household_day"} <= modules


class TestCalendarIsUnknownBeforeCapture:
    def _wide(self, con, captured_from):
        con.execute(f"CREATE TABLE context_features AS {reg.features_query(_available(con))}")
        con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")
        return reg.context_hourly_query(_available(con))

    def test_hours_before_capture_are_null_not_zero(self):
        captured = START + timedelta(hours=48)
        con = _con(captured_from=captured)
        wide = self._wide(con, captured)

        before = con.execute(
            f"SELECT COUNT(*), COUNT(calendar_busy_minutes) FROM ({wide}) WHERE bucket_utc < ?",
            [captured],
        ).fetchone()
        after_nulls = con.execute(
            f"SELECT COUNT(*) FROM ({wide}) WHERE bucket_utc >= ? "
            "AND calendar_busy_minutes IS NULL",
            [captured],
        ).fetchone()[0]

        assert before == (48, 0)  # unknown, not free
        assert after_nulls == 0  # captured: an hour with no event is a real 0

    def test_from_capture_on_the_values_are_exactly_the_old_ones(self):
        captured = START + timedelta(hours=48)
        con = _con(captured_from=captured)
        legacy = _legacy_context_hourly(True, True)
        wide = self._wide(con, captured)

        diff = con.execute(
            f"SELECT COUNT(*) FROM (SELECT * FROM ({legacy}) WHERE bucket_utc >= ? "
            f"EXCEPT SELECT * FROM ({wide}) WHERE bucket_utc >= ?)",
            [captured, captured],
        ).fetchone()[0]

        assert diff == 0

    def test_a_lake_with_no_capture_record_has_no_calendar_column_values(self):
        con = _con(with_calendar=True)
        con.execute("DROP TABLE calendar_capture")
        con.execute(f"CREATE TABLE context_features AS {reg.features_query(_available(con))}")
        con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")
        wide = reg.context_hourly_query(_available(con))

        n = con.execute(f"SELECT COUNT(calendar_busy_minutes) FROM ({wide})").fetchone()[0]

        assert n == 0


class TestForecastFeatures:
    def test_forecast_features_exist_in_the_long_table_not_the_wide_one(self):
        con = _con()
        available = _available(con, forecast=True)
        con.execute(f"CREATE TABLE context_features AS {reg.features_query(available)}")
        con.execute("CREATE VIEW g_context_features AS SELECT * FROM context_features")

        keys = {
            r[0]
            for r in con.execute("SELECT DISTINCT feature_key FROM context_features").fetchall()
        }
        wide = reg.context_hourly_query(available)
        cols = [d[0] for d in con.execute(f"SELECT * FROM ({wide}) LIMIT 0").description]

        assert {"forecast_temp_c", "forecast_rain_probability", "forecast_error_6h_c"} <= keys
        assert not {"forecast_temp_c", "forecast_error_6h_c"} & set(
            cols
        )  # context_hourly unchanged

    def test_the_forecast_error_is_the_observation_six_hours_later_minus_the_forecast(self):
        con = _con()
        available = _available(con, forecast=True)
        con.execute(f"CREATE TABLE context_features AS {reg.features_query(available)}")
        hour = START + timedelta(hours=30)

        got = con.execute(
            "SELECT value_num FROM context_features WHERE feature_key = 'forecast_error_6h_c' "
            "AND bucket_utc = ?",
            [hour],
        ).fetchone()[0]
        expected = con.execute(
            "SELECT (SELECT temperature_c FROM s_weather_hourly WHERE bucket_utc = ?) "
            "- (SELECT forecast_temp_c FROM s_weather_hourly WHERE bucket_utc = ?)",
            [hour + timedelta(hours=6), hour],
        ).fetchone()[0]

        assert got == pytest.approx(expected)

    def test_no_error_where_the_observation_six_hours_later_does_not_exist(self):
        con = _con()
        available = _available(con, forecast=True)
        con.execute(f"CREATE TABLE context_features AS {reg.features_query(available)}")
        last = START + timedelta(hours=HOURS - 1)

        n = con.execute(
            "SELECT COUNT(*) FROM context_features WHERE feature_key = 'forecast_error_6h_c' "
            "AND bucket_utc > ?",
            [last - timedelta(hours=6)],
        ).fetchone()[0]

        assert n == 0  # never an invented value for the future

    def test_forecast_features_are_not_built_when_weather_has_no_forecast_columns(self):
        con = _con()

        query = reg.features_query(_available(con, forecast=False))

        assert "forecast_temp_c" not in query and "forecast_error_6h_c" not in query

    def test_the_forecast_features_say_how_approximate_the_lead_is(self):
        by_key = {f.key: f for f in reg.REGISTRY}

        assert "target time is not stored" in by_key["forecast_temp_c"].provenance
        assert "Approximate" in by_key["forecast_error_6h_c"].description
