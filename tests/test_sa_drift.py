"""Tests for the drift detector (sa/learners/drift.py): a CUSUM over daily features that dates a
level shift, ignores bursts and weekday/weekend structure, and caps the profiled learner's
stability until the new regime is established."""

import random
from datetime import date, timedelta

from services.service_sa.sa.learners import drift

START = date(2026, 6, 1)  # a Monday


def _series(days, fn):
    return [(START + timedelta(days=i), fn(i, START + timedelta(days=i))) for i in range(days)]


def _noise(seed=3, scale=20.0):
    rnd = random.Random(seed)
    return lambda: rnd.gauss(0, scale)


class TestDetect:
    def test_too_short_is_not_tested(self):
        assert drift.detect(_series(drift.MIN_DAYS - 1, lambda i, d: 100.0)) is None

    def test_stationary_series_with_a_weekly_pattern_has_no_change(self):
        n = _noise()
        pts = _series(120, lambda i, d: (200.0 if d.weekday() >= 5 else 600.0) + n())

        result = drift.detect(pts, min_sigma=45.0)

        assert result["changes"] == [] and result["settled"]

    def test_a_level_shift_is_found_and_dated_to_where_it_began(self):
        n = _noise()
        shift_day = 50
        pts = _series(90, lambda i, d: (600.0 if i < shift_day else 250.0) + n())

        result = drift.detect(pts, daytype_of=lambda d: "work", min_sigma=45.0)

        (change,) = result["changes"]
        assert change["direction"] == "down" and change["shift_sigma"] < -2
        assert abs((change["start"] - (START + timedelta(days=shift_day))).days) <= 2
        assert change["alarm"] > change["start"]

    def test_a_one_day_burst_is_not_a_regime_change(self):
        n = _noise()
        pts = _series(90, lambda i, d: (600.0 if i != 50 else 0.0) + n())

        assert drift.detect(pts, daytype_of=lambda d: "work", min_sigma=45.0)["changes"] == []

    def test_a_flat_series_does_not_turn_a_wiggle_into_drift(self):
        pts = _series(60, lambda i, d: 0.0 if i < 40 else 30.0)  # 30 min against a 45 min floor

        assert drift.detect(pts, daytype_of=lambda d: "work", min_sigma=45.0)["changes"] == []

    def test_testing_resumes_in_the_new_regime(self):
        n = _noise()
        pts = _series(140, lambda i, d: (600.0 if i < 40 else 250.0 if i < 90 else 600.0) + n())

        result = drift.detect(pts, daytype_of=lambda d: "work", min_sigma=45.0)

        assert [c["direction"] for c in result["changes"]] == ["down", "up"]


class TestStability:
    def _result(self, change_start, s=0.0):
        return {
            "changes": [{"start": change_start}] if change_start else [],
            "s_plus": s,
            "s_minus": 0.0,
        }

    def test_no_change_is_full_stability(self):
        assert drift.stability_of(self._result(None), START) == 1.0

    def test_a_change_starts_low_and_recovers_over_four_weeks(self):
        day = date(2026, 8, 1)

        at_change = drift.stability_of(self._result(day), day)
        halfway = drift.stability_of(self._result(day), day + timedelta(days=14))
        recovered = drift.stability_of(self._result(day), day + timedelta(days=28))

        assert at_change == drift.STABILITY_AT_CHANGE
        assert at_change < halfway < recovered == 1.0

    def test_a_building_alarm_costs_at_most_the_building_penalty(self):
        assert drift.stability_of(self._result(None, s=50.0), START) == 1.0 - drift.BUILDING_PENALTY


class TestLearner:
    def _features(self):
        n = _noise()
        pts = _series(90, lambda i, d: (600.0 if i < 70 else 250.0) + n())
        return {("presence_profile", "user", "1"): {"feature": "minutes_home", "points": pts}}

    def test_fit_stores_the_change_and_a_recent_one_scores_as_an_inference(self):
        learner = drift.DriftLearner()
        (profile,) = learner.fit(self._features(), daytype_of=lambda d: "work")

        inference = learner.score(profile)

        assert profile.params["target_learner"] == "presence_profile"
        assert profile.stability < 1.0
        assert inference.kind == "drift" and inference.subject_id == "1"
        assert inference.observed["direction"] == "down"
        assert 0 < inference.confidence <= 1

    def test_an_old_change_is_remembered_but_not_announced(self):
        n = _noise()
        pts = _series(120, lambda i, d: (600.0 if i < 30 else 250.0) + n())
        learner = drift.DriftLearner()
        (profile,) = learner.fit(
            {("scalar_baseline", "series", "s"): {"feature": "daily_mean", "points": pts}},
            daytype_of=lambda d: "work",
        )

        assert profile.params["changes"] and profile.stability == 1.0
        assert learner.score(profile) is None


class _Cursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))


class _Conn:
    def __init__(self):
        self.cur = _Cursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


class TestApply:
    def test_only_lowered_profiles_are_written_and_only_when_they_would_drop(self):
        learner = drift.DriftLearner()
        profiles = learner.fit(TestLearner()._features(), daytype_of=lambda d: "work") + [
            drift.Profile(
                drift.NAME, "1", "user", "2", drift.SIGNAL, {"target_learner": "x"}, stability=1.0
            )
        ]
        conn = _Conn()

        lowered = drift.apply_stability(conn, profiles)

        assert lowered == 1 and len(conn.cur.statements) == 1
        sql, params = conn.cur.statements[0]
        assert "stability > %s" in sql and params[3:5] == ("user", "1")
