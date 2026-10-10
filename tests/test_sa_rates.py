"""Tests for the event-stream rate learner (sa/learners/rates.py): negative-binomial maths and
streams whose answer is known (a busy-by-day stream with one burst, a quiet stream, a sender that
goes wild)."""

import math
import random
from datetime import date, datetime, timedelta

import pytest

from services.service_sa.sa.learners import rates

START = date(2026, 9, 1)


def _points(days, fn, window="hour"):
    pts = []
    for i in range(days):
        d = START + timedelta(days=i)
        if window == "day":
            pts.append({"date": d, "hour": 0, "n": fn(d, 0), "t": None})
            continue
        for h in range(24):
            t = datetime.combine(d, datetime.min.time()) + timedelta(hours=h + 4)
            pts.append({"date": d, "hour": h, "n": fn(d, h), "t": t})
    return pts


def _busy_by_day(seed=1):
    rnd = random.Random(seed)

    def fn(d, h):
        base = 4.0 if 9 <= h < 17 else 0.3
        return int(rnd.random() < 0.5) + sum(rnd.random() < base / 8 for _ in range(8))

    return fn


class TestNegativeBinomial:
    def test_pmf_sums_to_one(self):
        total = sum(math.exp(rates.nb_logpmf(k, 3.0, 2.0)) for k in range(400))
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_upper_and_lower_tails_partition_the_mass(self):
        for k in (0, 1, 5, 12):
            up = rates.nb_upper(k + 1, 3.0, 2.0)
            low = rates.nb_lower(k, 3.0, 2.0)
            assert up + low == pytest.approx(1.0, abs=1e-9)

    def test_tail_is_tiny_and_finite_far_out(self):
        p = rates.nb_upper(60, 5.0, 2.0)
        assert 0 < p < 1e-6

    def test_zero_mean(self):
        assert rates.nb_upper(1, 1.0, 0.0) == 0.0 and rates.nb_upper(0, 1.0, 0.0) == 1.0


class TestFit:
    def _profile(self, fn=None, days=40, window="hour", key="event:x"):
        pts = _points(days, fn or _busy_by_day(), window)
        return rates.fit_stream(key, window, pts, pts[-1]["date"], {}), pts

    def test_learns_the_daily_shape(self):
        profile, _ = self._profile()
        cells = profile.params["cells"]["work"]
        assert cells[12] > 3 * cells[3]

    def test_too_few_events_or_days_gives_no_profile(self):
        pts = _points(3, lambda d, h: 1)
        assert rates.fit_stream("e", "hour", pts, pts[-1]["date"], {}) is None
        rare = _points(40, lambda d, h: 1 if (d.day == 3 and h == 5) else 0)
        assert rates.fit_stream("e", "hour", rare, rare[-1]["date"], {}) is None

    def test_weekend_cells_are_separate_from_weekday_cells(self):
        off = {
            START + timedelta(days=i): "off"
            for i in range(40)
            if (START + timedelta(days=i)).weekday() >= 5
        }
        pts = _points(40, lambda d, h: 6 if (d.weekday() >= 5 and h == 10) else 0)
        profile = rates.fit_stream("e", "hour", pts, pts[-1]["date"], off)
        assert profile.params["cells"]["off"][10] > 10 * profile.params["cells"]["work"][10] + 1

    def test_bursty_stream_gets_more_dispersion_than_a_steady_one(self):
        rnd = random.Random(5)
        steady, _ = self._profile(lambda d, h: 2 + (rnd.random() < 0.3))
        burst, _ = self._profile(lambda d, h: 20 if rnd.random() < 0.04 else 0)
        assert burst.params["phi"] > steady.params["phi"] * 3

    def test_confidence_terms_are_populated(self):
        profile, _ = self._profile()
        assert profile.n_eff > 10 and 0 <= profile.stability <= 1


class TestScore:
    def _setup(self):
        pts = _points(40, _busy_by_day(2))
        profile = rates.fit_stream("event:x", "hour", pts, pts[-1]["date"], {})
        return profile, rates.RateLearner()

    def _state(self, count, hour=12):
        return {
            "count": count,
            "hour": hour,
            "daytype": "work",
            "window_start": datetime(2026, 10, 12, hour, 0),
        }

    def test_a_normal_count_is_quiet(self):
        profile, learner = self._setup()
        assert learner.score(profile, self._state(4), datetime(2026, 10, 12, 13)) is None

    def test_a_burst_fires_with_probability_surprise_and_confidence(self):
        profile, learner = self._setup()
        inf = learner.score(profile, self._state(40), datetime(2026, 10, 12, 13))
        assert inf.observed["direction"] == "high"
        assert inf.probability <= rates.P_FLAG and inf.surprise > 13
        assert 0 < inf.confidence <= 1 and inf.subject_type == "stream"

    def test_a_dead_quiet_busy_hour_fires_low(self):
        pts = _points(40, lambda d, h: 12)
        profile = rates.fit_stream("event:x", "hour", pts, pts[-1]["date"], {})
        inf = rates.RateLearner().score(profile, self._state(0), datetime(2026, 10, 12, 13))
        assert inf is not None and inf.observed["direction"] == "low"

    def test_quiet_on_a_quiet_hour_is_not_an_anomaly(self):
        profile, learner = self._setup()
        assert learner.score(profile, self._state(0, hour=3), datetime(2026, 10, 12, 4)) is None

    def test_small_excess_over_a_tiny_expectation_is_ignored(self):
        profile, learner = self._setup()
        assert learner.tail(profile, self._state(2, hour=3)) is None


class TestSenders:
    def test_a_sender_going_wild_in_a_day_fires(self):
        rnd = random.Random(7)
        pts = _points(60, lambda d, h: int(rnd.random() < 0.6), "day")
        profile = rates.fit_stream("sender:gmail:a@b.com", "day", pts, pts[-1]["date"], {})
        assert profile.subject_type == "sender"
        state = {"count": 40, "hour": 0, "daytype": "work", "window_start": datetime(2026, 10, 12)}
        inf = rates.RateLearner().score(profile, state, datetime(2026, 10, 12, 12))
        assert inf is not None and inf.window_end - inf.window_start == timedelta(days=1)

    def test_a_rare_sender_is_not_modelled(self):
        pts = _points(60, lambda d, h: 1 if d.day == 5 else 0, "day")
        assert rates.fit_stream("s", "day", pts, pts[-1]["date"], {}) is None
