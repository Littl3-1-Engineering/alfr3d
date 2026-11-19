"""The covariate probe (sa/covariate_probe.py): the pure parts, on synthetic data with a known
answer. Its job is to say where a covariate is worth an opt-in PR, so the two ways it can mislead
are tested directly: a planted relationship must be found, and a sparse target must be flagged as
low power instead of reported as 'no relationship'."""

import random
from datetime import datetime, timedelta

from services.service_sa.sa import covariate_probe as probe

T0 = datetime(2026, 11, 2)  # a Monday


def _rows(n, fn):
    out = []
    for i in range(n):
        t = T0 + timedelta(hours=i)
        out.append((t, t.weekday(), t.hour, fn(i, t)))
    return out


def test_the_hour_of_week_structure_is_removed():
    rows = _rows(24 * 28, lambda i, t: 5.0 if t.hour == 8 else 1.0)
    residual = probe.residual_by_hour_of_week(rows)
    assert all(abs(v) < 1e-9 for v in residual.values())


def test_anomaly_is_relative_to_the_hour_of_day():
    series = {T0 + timedelta(hours=i): float(10 + (i % 24)) for i in range(24 * 5)}
    assert all(abs(v) < 1e-9 for v in probe.anomaly_by_hour_of_day(series).values())
    series[T0 + timedelta(hours=30)] += 4
    assert max(probe.anomaly_by_hour_of_day(series).values()) > 3


def test_raw_series_keep_a_real_zero():
    series = {T0: 0.0, T0 + timedelta(hours=1): None, T0 + timedelta(hours=2): 3.0}
    assert probe.anomaly_or_raw(series, False) == {T0: 0.0, T0 + timedelta(hours=2): 3.0}


def _feature_and_target(slope, n=24 * 14, seed=2):
    rng = random.Random(seed)
    feature, x = {}, 0.0
    target_rows = []
    for i in range(n):
        t = T0 + timedelta(hours=i)
        x += rng.gauss(0, 0.5)
        feature[t] = x
        target_rows.append((t, t.weekday(), t.hour, 20 + slope * x + rng.gauss(0, 0.5)))
    return feature, target_rows


FAST = dict(permutations=49)


def test_a_planted_relationship_is_found_and_a_null_is_not():
    feature, rows = _feature_and_target(1.0)
    found = probe.probe_target(rows, [("signal", 0, feature)], **FAST)
    assert found["findings"][0]["status"] == "effect"
    assert found["method"] == "slope"

    feature, rows = _feature_and_target(0.0, seed=9)
    null = probe.probe_target(rows, [("signal", 0, feature)], **FAST)
    assert null["findings"][0]["status"] == "insufficient_evidence"


def test_a_sparse_target_goes_to_the_rate_screen_and_a_planted_shift_is_found():
    rng = random.Random(4)
    feature, x = {}, 0.0
    rows = []
    for i in range(24 * 60):
        t = T0 + timedelta(hours=i)
        x = 0.9 * x + rng.gauss(0, 1)
        feature[t] = x
        high = x > 0.8
        rows.append(
            (t, t.weekday(), t.hour, 1.0 if rng.random() < (0.30 if high else 0.04) else 0.0)
        )
    result = probe.probe_target(rows, [("signal", 0, feature)], permutations=99)
    assert result["method"] == "rates" and result["zero_share"] > 0.7
    assert result["findings"][0]["status"] == "effect"
    assert result["findings"][0]["rate_shift"] > 0.1
    text = probe.render(
        {"candidates": ["signal@0h"], "targets": {"event:x": result}, "day_level": {}}
    )
    assert "rates" in text and "effect=" in text


def test_a_sparse_null_is_not_an_effect():
    rng = random.Random(11)
    feature, _ = _feature_and_target(0.0, n=24 * 60)
    rows = _rows(24 * 60, lambda i, t: 1.0 if rng.random() < 0.08 else 0.0)
    result = probe.probe_target(rows, [("signal", 0, feature)], permutations=99)
    assert result["method"] == "rates"
    assert result["findings"][0]["status"] == "insufficient_evidence"
