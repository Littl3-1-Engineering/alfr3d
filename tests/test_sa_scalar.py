"""Tests for the scalar-series learner (sa/learners/scalar.py): synthetic series whose answer is
known, so each assertion checks a design decision (robust sigma, hour effects, local level,
covariates that must earn their place, counters and constants excluded)."""

import math
import random
from datetime import date, datetime, timedelta

import pytest

from services.service_sa.sa.learners import scalar

START = datetime(2026, 9, 1, 0, 0)


def _series(hours, fn, coverage=1.0):
    pts = []
    for i in range(hours):
        t = START + timedelta(hours=i)
        pts.append(
            {"t": t, "date": t.date(), "hour": t.hour, "value": fn(i, t), "coverage": coverage}
        )
    return pts


def _daily(i, t):
    return 20 + 2 * math.sin((t.hour - 6) / 24 * 2 * math.pi)


def _noisy(seed=1, sd=0.3):
    rnd = random.Random(seed)
    return lambda i, t: _daily(i, t) + rnd.gauss(0, sd)


def _ref(pts):
    return pts[-1]["date"]


class TestStatistics:
    def test_weighted_median_respects_weights(self):
        assert scalar.weighted_median([1, 2, 3], [1, 1, 10]) == 3
        assert scalar.weighted_median([], []) is None

    def test_mad_sigma_ignores_a_wild_outlier(self):
        values = [0.0] * 50 + [1.0, -1.0] * 25 + [1_800_000]
        _, sigma = scalar.weighted_mad_sigma(values, [1.0] * len(values))
        assert sigma < 2

    def test_theil_sen_recovers_slope_despite_outliers(self):
        xs = list(range(50))
        ys = [2 * x for x in xs]
        ys[10] = 500
        assert scalar.theil_sen(xs, ys) == pytest.approx(2, abs=0.05)

    def test_two_sided_p(self):
        assert scalar.two_sided_p(0) == pytest.approx(1)
        assert scalar.two_sided_p(1.96) == pytest.approx(0.05, abs=0.001)

    def test_long_subject_ids_are_shortened_stably_and_distinctly(self):
        a, b = "ha:" + "x" * 80 + "a", "ha:" + "x" * 80 + "b"
        assert len(scalar.subject_id_for(a)) <= 64
        assert scalar.subject_id_for(a) != scalar.subject_id_for(b)
        assert scalar.subject_id_for("short") == "short"


class TestFit:
    def test_learns_the_hour_effect(self):
        pts = _series(24 * 20, _noisy())
        profile = scalar.fit_points("s", pts, _ref(pts))
        effects = profile.params["effects"]
        assert abs(sum(effects)) < 1e-3
        assert effects[12] > effects[0]  # sin peaks mid-day, trough near midnight
        assert profile.params["sigma"] == pytest.approx(0.3, abs=0.2)

    def test_too_little_history_gives_no_profile(self):
        pts = _series(24, _noisy())
        assert scalar.fit_points("s", pts, _ref(pts)) is None

    def test_constant_series_is_not_modelled(self):
        pts = _series(24 * 10, lambda i, t: 90.0)
        assert scalar.fit_points("battery", pts, _ref(pts)) is None

    def test_monotonic_counter_is_not_modelled(self):
        pts = _series(24 * 10, lambda i, t: 1000.0 + i * 3600)
        assert scalar.fit_points("uptime", pts, _ref(pts)) is None

    def test_low_coverage_hours_are_not_observations(self):
        pts = _series(24 * 10, _noisy(), coverage=0.2)
        assert scalar.fit_points("s", pts, _ref(pts)) is None

    def test_sigma_survives_garbage_readings(self):
        base = _noisy()
        pts = _series(24 * 20, lambda i, t: 1_800_000 if i % 97 == 0 else base(i, t))
        profile = scalar.fit_points("ping", pts, _ref(pts))
        assert profile.params["sigma"] < 5

    def test_stability_falls_when_recent_noise_grows(self):
        rnd = random.Random(2)
        pts = _series(
            24 * 30,
            lambda i, t: _daily(i, t) + rnd.gauss(0, 0.3 if i < 24 * 22 else 3.0),
        )
        calm = scalar.fit_points("s", _series(24 * 30, _noisy(3)), date(2026, 9, 30))
        noisy = scalar.fit_points("s", pts, date(2026, 9, 30))
        assert noisy.stability < calm.stability
        assert calm.stability > 0.8

    def test_covariate_stays_off_without_overlap(self):
        pts = _series(24 * 20, _noisy())
        cov = [{"t": p["t"], "value": 5.0, "date": p["date"], "hour": p["hour"]} for p in pts[:10]]
        profile = scalar.fit_points("s", pts, _ref(pts), covariate=cov)
        assert profile.params["beta"] is None
        assert profile.params["covariate"]["used"] is False


class TestScore:
    def _profile(self):
        pts = _series(24 * 20, _noisy(4))
        return scalar.fit_points("indoor", pts, _ref(pts)), pts

    def _state(self, pts, value):
        by_time = {p["t"]: p for p in pts}
        t = pts[-1]["t"] + timedelta(hours=1)
        recent = [
            (
                lag,
                by_time[t - timedelta(hours=lag)]["hour"],
                by_time[t - timedelta(hours=lag)]["value"],
            )
            for lag in range(1, 25)
            if t - timedelta(hours=lag) in by_time
        ]
        return {"value": value, "recent": recent, "local_dt": t}, t

    def test_a_normal_value_does_not_fire(self):
        profile, pts = self._profile()
        state, t = self._state(pts, _daily(0, pts[-1]["t"] + timedelta(hours=1)))
        assert scalar.ScalarLearner().score(profile, state, t) is None

    def test_a_big_jump_fires_with_probability_surprise_and_confidence(self):
        profile, pts = self._profile()
        state, t = self._state(pts, _daily(0, pts[-1]["t"] + timedelta(hours=1)) + 8)
        inf = scalar.ScalarLearner().score(profile, state, t)
        assert inf.kind == "deviation" and inf.observed["direction"] == "high"
        assert inf.probability < 1e-3 and inf.surprise > 10
        assert 0 < inf.confidence <= 1
        assert inf.subject_id == "indoor"

    def test_a_slow_drift_is_tracked_by_the_level_and_does_not_fire(self):
        """The reason for the local level: +3 C over the last day is weather, not an alarm."""
        profile, pts = self._profile()
        shifted = [dict(p, value=p["value"] + 3) for p in pts[-24:]]
        state, t = self._state(shifted, _daily(0, pts[-1]["t"] + timedelta(hours=1)) + 3)
        assert scalar.ScalarLearner().score(profile, state, t) is None

    def test_no_recent_data_means_no_score(self):
        profile, pts = self._profile()
        state, t = self._state(pts, 99)
        state["recent"] = []
        assert scalar.ScalarLearner().score(profile, state, t) is None
