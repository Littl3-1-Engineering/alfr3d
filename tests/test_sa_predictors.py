"""Predictor registry and the proof predictor `switch_usual_state` (sa/predictors.py). Known
schedules must be predicted, an irregular switch must not be, and below the floors it must say
'insufficient evidence' and nothing else. Nothing here, or in the module, can reach a device."""

import random
from datetime import date, datetime, timedelta

import pytest

from services.service_sa.sa import predictors

UTC = "UTC"
D0 = datetime(2026, 10, 1)  # a Thursday


def _schedule(days, on_hour=17, off_hour=23, weekend_off=False, noise=0.0, seed=1):
    """Transitions of a lamp that is on from on_hour to off_hour each day (UTC = local here)."""
    rng = random.Random(seed)
    out = []
    for d in range(days):
        day = D0 + timedelta(days=d)
        if weekend_off and day.weekday() >= 5:
            out.append((day + timedelta(hours=1), "off"))  # stays off all weekend
            continue
        if rng.random() < noise:
            continue
        out.append((day + timedelta(hours=on_hour), "on"))
        out.append((day + timedelta(hours=off_hour), "off"))
    return out


def _rows(transitions, days):
    end = D0 + timedelta(days=days)
    return predictors.hourly_states(transitions, end, UTC)


class TestHourlyStates:
    def test_on_fraction_follows_the_state_across_partial_hours(self):
        tr = [
            (D0 + timedelta(hours=10, minutes=30), "on"),
            (D0 + timedelta(hours=12, minutes=15), "off"),
        ]
        rows = predictors.hourly_states(tr, D0 + timedelta(hours=14), UTC)
        frac = {h: f for _d, h, _k, f in rows}
        assert frac[10] == pytest.approx(0.5) and frac[11] == 1.0
        assert frac[12] == pytest.approx(0.25) and frac[13] == 0.0

    def test_the_series_starts_at_the_first_observation_and_ignores_unavailable(self):
        tr = [(D0 + timedelta(hours=5), "unavailable"), (D0 + timedelta(hours=6), "on")]
        rows = predictors.hourly_states(tr, D0 + timedelta(hours=9), UTC)
        assert [h for _d, h, *_ in rows] == [6, 7, 8]  # nothing is invented before the first state
        assert predictors.hourly_states([], D0, UTC) == []

    def test_local_time_and_day_kind_follow_the_zone(self):
        tr = [(datetime(2026, 10, 3, 3, 0), "on")]  # Saturday 03:00 UTC = Friday 23:00 in Toronto
        rows = predictors.hourly_states(tr, datetime(2026, 10, 3, 5), "America/Toronto")
        assert rows[0][:3] == (date(2026, 10, 2), 23, "weekday")


class TestEvaluate:
    def test_a_regular_lamp_has_clear_skill(self):
        rows = _rows(_schedule(40), 40)
        score = predictors.evaluate(rows)
        assert score["status"] == "scored" and score["skill"] > 0.8
        assert score["brier"] < score["baseline_brier"]

    def test_an_irregular_lamp_has_no_skill_to_speak_of(self):
        rng = random.Random(7)
        tr = []
        for d in range(40):
            for h in range(24):
                tr.append((D0 + timedelta(days=d, hours=h), "on" if rng.random() < 0.3 else "off"))
        score = predictors.evaluate(_rows(tr, 40))
        assert score["status"] == "scored" and score["skill"] < 0.15

    def test_below_the_floors_it_says_insufficient_evidence_and_nothing_else(self):
        short = predictors.evaluate(_rows(_schedule(8), 8))
        assert short["status"] == "insufficient_evidence" and "training days" in short["reason"]
        assert "skill" not in short
        few_test = predictors.evaluate(
            _rows(_schedule(16), 16)
        )  # 11 train days, 5 test days: 120h ok
        assert few_test["status"] == "scored"
        thin = predictors.evaluate(_rows(_schedule(14), 14))  # 9 train days
        assert thin["status"] == "insufficient_evidence"

    def test_the_split_is_in_time_order_so_the_future_is_never_trained_on(self):
        rows = _rows(_schedule(40), 40)
        score = predictors.evaluate(rows)
        days = sorted({d for d, *_ in rows})
        assert score["train_days"] == int(len(days) * 0.7)
        assert score["test_hours"] == sum(
            1 for r in rows if r[0] in set(days[score["train_days"] :])
        )


class TestPredict:
    def test_a_regular_lamp_is_predicted_on_in_its_usual_hours_and_off_otherwise(self):
        rows = _rows(_schedule(40), 40)
        on = predictors.predict(rows, "switch.lamp", 20, "weekday")
        off = predictors.predict(rows, "switch.lamp", 4, "weekday")
        assert on.probability > 0.9 and off.probability < 0.1
        assert on.predictor == "switch_usual_state" and on.subject == "switch.lamp"
        assert any("comparable weekday hours at 20:00" in b for b in on.because)
        assert any("held-out skill" in b for b in on.because)

    def test_the_weekend_can_differ_from_the_weekday(self):
        rows = _rows(_schedule(60, weekend_off=True), 60)
        weekday = predictors.predict(rows, "s", 20, "weekday")
        weekend = predictors.predict(rows, "s", 20, "weekend")
        assert weekday.probability > 0.9 and weekend.probability < 0.2

    def test_confidence_uses_the_shared_contract_and_rises_with_evidence(self):
        small = predictors.predict(_rows(_schedule(16), 16), "s", 20, "weekday")
        large = predictors.predict(_rows(_schedule(60), 60), "s", 20, "weekday")
        assert 0.0 < small.confidence < large.confidence <= 1.0

    def test_no_skill_or_no_evidence_means_no_prediction(self):
        rng = random.Random(3)
        tr = [
            (D0 + timedelta(days=d, hours=h), "on" if rng.random() < 0.5 else "off")
            for d in range(40)
            for h in range(24)
        ]
        assert predictors.predict(_rows(tr, 40), "s", 20, "weekday") is None
        assert predictors.predict(_rows(_schedule(5), 5), "s", 20, "weekday") is None

    def test_noise_that_beats_the_usual_rate_by_rounding_alone_does_not_speak(self):
        assert predictors.MIN_SKILL >= 0.05
        rng = random.Random(3)
        tr = [
            (D0 + timedelta(days=d, hours=h), "on" if rng.random() < 0.5 else "off")
            for d in range(40)
            for h in range(24)
        ]
        score = predictors.evaluate(_rows(tr, 40))
        assert 0.0 <= score["skill"] < predictors.MIN_SKILL  # a hair above zero, still silent


class TestRegistryAndSafety:
    def test_the_proof_predictor_is_registered_with_its_floors(self):
        (p,) = predictors.REGISTRY
        assert p.key == "switch_usual_state"
        assert (p.min_train_days, p.min_test_hours) == (10, 72)
        assert "ON" in p.predicts and "any cause" in p.history

    def test_the_module_cannot_reach_a_device(self):
        import inspect

        source = inspect.getsource(predictors)
        for forbidden in (
            "device_control",
            "control_iot_device",
            "get_producer",
            "requests",
            "pymysql",
        ):
            assert forbidden not in source

    def test_no_lake_is_an_empty_result_not_an_error(self, tmp_path):
        assert predictors.evaluate_lake(tmp_path) == {}
