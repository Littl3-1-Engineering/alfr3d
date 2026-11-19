"""The nightly discovery screen (sa/screen.py), end to end on a small Parquet lake with planted
relationships. The two properties that matter: a relationship we planted is found and one we did
not is not, and every declared target produces rows whatever is missing."""

import random
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from services.service_sa.sa import covariates, screen, targets

T0 = datetime(2026, 9, 7)  # a Monday
HOURS = 24 * 60
RUN = datetime(2026, 11, 19, 3, 30)


def _write(lake, layer, table, sql, con=None):
    con = con or duckdb.connect()
    path = Path(lake) / layer / table
    path.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({sql}) TO '{path / 'part-0.parquet'}' (FORMAT PARQUET)")


def _insert(con, table, rows):
    """One bulk INSERT (rows are tuples of SQL literals): thousands of single inserts are slow."""
    for i in range(0, len(rows), 1000):
        values = ",".join("(" + ",".join(str(x) for x in r) + ")" for r in rows[i : i + 1000])
        con.execute(f"INSERT INTO {table} VALUES {values}")


def build_lake(
    lake,
    seed=1,
    planted=True,
    features=("outdoor_temp_c", "outdoor_humidity_pct"),
    hours=HOURS,
    trend=False,
):
    """One owner, one resident, two guests over `hours` hours. With `planted`, a guest is home far
    more often when the outdoor temperature anomaly is in its top third; otherwise guests are home
    at random. The humidity series is always independent noise."""
    rng = random.Random(seed)
    con = duckdb.connect()
    temp, x = [], 0.0
    for _ in range(hours):
        x = 0.9 * x + rng.gauss(0, 1)
        temp.append(x)
    if trend:  # a slow cooling the guests have nothing to do with
        temp = [x - 12.0 * h / hours for h, x in enumerate(temp)]
    cut = sorted(temp)[(2 * hours) // 3]
    grid = []
    for h in range(hours):
        t = T0 + timedelta(hours=h)
        hour = h % 24
        for uid, name, away in ((1, "owner", range(9, 18)), (2, "res", range(8, 13))):
            grid.append((uid, name, t, 0 if hour in away else 60))
        p = 0.05 + (0.45 if planted and temp[h] > cut else 0.0)
        if trend:  # guests drift from rare to common over the same weeks, for unrelated reasons
            p = 0.04 + 0.35 * h / hours
        grid.append((3, "g1", t, 60 if rng.random() < p else 0))
        grid.append((4, "g2", t, 60 if rng.random() < 0.04 else 0))
    con.execute("CREATE TABLE g (user_id INT, username VARCHAR, bucket_utc TIMESTAMP, m DOUBLE)")
    _insert(con, "g", [(u, f"'{n}'", f"TIMESTAMP '{t}'", m) for u, n, t, m in grid])
    _write(
        lake,
        "gold",
        "presence_grid",
        "SELECT user_id, username, bucket_utc, m AS minutes_home, true AS observed FROM g",
        con,
    )
    _write(
        lake,
        "silver",
        "presence_intervals",
        "SELECT * FROM (VALUES (1,'owner'),(2,'resident'),(3,'guest'),(4,'guest')) "
        "t(user_id, user_type)",
        con,
    )
    con.execute("CREATE TABLE ch (bucket_utc TIMESTAMP, dow_local INT, hour_local INT)")
    _insert(
        con,
        "ch",
        [
            (f"TIMESTAMP '{T0 + timedelta(hours=h)}'", (T0 + timedelta(hours=h)).weekday(), h % 24)
            for h in range(hours)
        ],
    )
    _write(lake, "gold", "context_hourly", "SELECT * FROM ch", con)
    if features:
        con.execute(
            "CREATE TABLE cf (feature_key VARCHAR, bucket_utc TIMESTAMP, value_num DOUBLE, "
            "value_text VARCHAR)"
        )
        noise = random.Random(seed + 100)
        rows = []
        for h in range(hours):
            t = T0 + timedelta(hours=h)
            if "outdoor_temp_c" in features:
                rows.append(("outdoor_temp_c", t, 10.0 + temp[h], None))
            if "outdoor_humidity_pct" in features:
                rows.append(("outdoor_humidity_pct", t, 50 + noise.gauss(0, 5), None))
        _insert(con, "cf", [(f"'{k}'", f"TIMESTAMP '{t}'", v, "NULL") for k, t, v, _ in rows])
        _write(lake, "gold", "context_features", "SELECT * FROM cf", con)
    return lake


FAST = dict(permutations=covariates.PERMUTATIONS)


def _by(rows, target, feature=None, lag=None):
    return [
        r
        for r in rows
        if r["target_key"] == target
        and (feature is None or r["feature_key"] == feature)
        and (lag is None or r["lag_hours"] == lag)
    ]


@pytest.fixture(scope="module")
def planted_rows(tmp_path_factory):
    lake = build_lake(tmp_path_factory.mktemp("planted"), seed=3, planted=True)
    return screen.run_screen(lake, now=RUN, **FAST)


@pytest.fixture(scope="module")
def null_rows(tmp_path_factory):
    lake = build_lake(tmp_path_factory.mktemp("null"), seed=3, planted=False)
    return screen.run_screen(lake, now=RUN, **FAST)


class TestPlantedAndNull:
    def test_a_planted_relationship_is_found(self, planted_rows):
        (found,) = _by(planted_rows, "guests_home", "outdoor_temp_c", 0)
        assert found["status"] == "effect"
        assert found["method"] == "rates" and found["effect"] > 0.1
        assert found["p_adjusted"] <= covariates.ALPHA
        assert found["evidence"]["transform"] == "anomaly"
        assert found["n"] > 1000

    def test_the_independent_series_is_not(self, planted_rows):
        for r in _by(planted_rows, "guests_home", "outdoor_humidity_pct"):
            assert r["status"] != "effect", r

    def test_a_planted_null_finds_nothing_anywhere(self, null_rows):
        assert [r for r in null_rows if r["status"] == "effect"] == []

    def test_the_other_targets_run_and_do_not_invent_effects(self, planted_rows):
        # house_empty and away_minutes do not depend on temperature in this lake
        for key in ("house_empty", "away_minutes"):
            rows = _by(planted_rows, key)
            assert rows and {r["method"] for r in rows} == {
                "rates" if key == "house_empty" else "slope"
            }
            assert [r for r in rows if r["status"] == "effect"] == [], key


class TestSharedTrendIsNotACause:
    def test_a_feature_and_an_outcome_that_merely_drift_together_are_not_an_effect(self, tmp_path):
        # Temperature cools and guests become more frequent over the same 60 days, independently.
        # Measured against the whole-history mean this passes as a strong "weather effect"; measured
        # against the previous week, as the screen does, the trend is gone and so is the finding.
        build_lake(tmp_path, seed=11, planted=False, trend=True)
        rows = screen.run_screen(tmp_path, now=RUN, **FAST)
        assert [r for r in _by(rows, "guests_home") if r["status"] == "effect"] == []

    def test_the_trailing_anomaly_removes_a_trend_the_whole_history_mean_keeps(self):
        hours = [T0 + timedelta(hours=h) for h in range(HOURS)]
        series = {t: 10.0 - 12.0 * h / HOURS for h, t in enumerate(hours)}
        by_hour = {}
        for t, v in series.items():
            by_hour.setdefault(t.hour, []).append(v)
        mean = {h: sum(v) / len(v) for h, v in by_hour.items()}
        whole = {t: v - mean[t.hour] for t, v in series.items()}  # the superseded definition
        local = screen.anomaly_vs_trailing_week(series)
        spread = lambda d: max(d.values()) - min(d.values())  # noqa: E731
        assert spread(whole) > 10 and spread(local) < 1e-6


class TestEveryTargetAlwaysReports:
    def test_every_declared_target_and_candidate_is_covered(self, planted_rows):
        for t in targets.REGISTRY:
            rows = _by(planted_rows, t.key)
            assert {(r["feature_key"], r["lag_hours"]) for r in rows} == {
                (f, lag) for f, lag, _ in targets.expanded(t)
            }, t.key

    def test_a_feature_with_no_data_says_so(self, planted_rows):
        (r,) = _by(planted_rows, "guests_home", "forecast_rain_probability", 0)
        assert r["status"] == "insufficient_evidence"
        assert r["reason"] == "the feature has no data in the lake yet"
        assert r["n"] == 0 and r["effect"] is None

    def test_no_context_features_table_still_reports_every_candidate(self, tmp_path):
        build_lake(tmp_path, features=())
        rows = screen.run_screen(tmp_path, now=RUN, **FAST)
        for t in targets.REGISTRY:
            assert len(_by(rows, t.key)) == len(targets.expanded(t))
        assert all(r["status"] == "insufficient_evidence" for r in rows)

    def test_no_presence_tables_gives_one_row_per_target(self, tmp_path):
        rows = screen.run_screen(tmp_path, now=RUN, **FAST)
        assert [r["target_key"] for r in rows] == [t.key for t in targets.REGISTRY]
        assert all(r["feature_key"] == screen.ALL for r in rows)
        assert all("no data" in r["reason"] for r in rows)

    def test_missing_context_hourly_is_reported_not_guessed(self, tmp_path):
        build_lake(tmp_path)
        (Path(tmp_path) / "gold" / "context_hourly" / "part-0.parquet").unlink()
        rows = screen.run_screen(tmp_path, now=RUN, **FAST)
        assert len(rows) == len(targets.REGISTRY)
        assert all("context_hourly is missing" in r["reason"] for r in rows)

    def test_a_misdeclared_kind_is_refused_up_front(self, tmp_path):
        build_lake(tmp_path)
        wrong = replace(
            next(t for t in targets.REGISTRY if t.key == "away_minutes"), kind=targets.BINARY
        )
        with pytest.raises(ValueError, match="declared binary"):
            screen.run_screen(tmp_path, now=RUN, registry=(wrong,), **FAST)

    def test_a_kind_that_only_fails_on_real_data_is_reported_and_skipped(
        self, tmp_path, monkeypatch
    ):
        # the synthetic lake cannot catch every mismatch: the real data's own shape is checked too
        build_lake(tmp_path)
        wrong = replace(
            next(t for t in targets.REGISTRY if t.key == "away_minutes"), kind=targets.BINARY
        )
        monkeypatch.setattr(screen.targets, "validate_queries", lambda registry: [])
        rows = screen.run_screen(tmp_path, now=RUN, registry=(wrong,), **FAST)
        assert len(rows) == 1 and "target kind does not fit" in rows[0]["reason"]
        assert rows[0]["status"] == "insufficient_evidence"


class TestNeverManufacturesSignificance:
    def test_every_row_is_well_formed(self, planted_rows):
        for r in planted_rows:
            assert r["status"] in screen.STATUSES
            assert r["status"] == "effect" or r["reason"]
            if r["status"] == "effect":
                assert r["effect"] is not None and r["p_adjusted"] <= covariates.ALPHA
                assert r["improvement"] >= covariates.RATE_MIN_IMPROVEMENT or r["method"] == "slope"
            assert r["run_date"] == RUN.date() and r["computed_at"] == RUN

    def test_a_run_is_reproducible(self, tmp_path):
        build_lake(tmp_path, seed=5)
        assert screen.run_screen(tmp_path, now=RUN, **FAST) == screen.run_screen(
            tmp_path, now=RUN, **FAST
        )

    def test_it_refuses_to_run_on_an_unsound_registry(self, tmp_path):
        build_lake(tmp_path)
        wide = replace(
            targets.REGISTRY[0],
            candidates=(targets.Candidate("outdoor_temp_c", tuple(range(12)), targets.ANOMALY),),
        )
        with pytest.raises(ValueError, match="over the budget"):
            screen.run_screen(tmp_path, now=RUN, registry=(wide,), **FAST)

    def test_it_refuses_a_target_offering_a_restricted_feature(self, tmp_path):
        build_lake(tmp_path)
        bad = replace(
            targets.REGISTRY[0], candidates=(targets.Candidate("precise_location", (0,)),)
        )
        with pytest.raises(ValueError, match="not visible to a learner"):
            screen.run_screen(tmp_path, now=RUN, registry=(bad,), **FAST)

    def test_summarize_counts_by_target(self, planted_rows):
        summary = screen.summarize(planted_rows)
        assert set(summary) == {t.key for t in targets.REGISTRY}
        assert summary["guests_home"]["effect"] >= 1
