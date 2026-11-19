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
    assert not found["low_power"]

    feature, rows = _feature_and_target(0.0, seed=9)
    null = probe.probe_target(rows, [("signal", 0, feature)], **FAST)
    assert null["findings"][0]["status"] == "insufficient_evidence"


def test_a_sparse_target_is_flagged_not_reported_as_no_relationship():
    rng = random.Random(4)
    feature, _ = _feature_and_target(0.0)
    rows = _rows(24 * 14, lambda i, t: 1.0 if rng.random() < 0.05 else 0.0)
    result = probe.probe_target(rows, [("signal", 0, feature)], **FAST)
    assert result["zero_share"] > 0.9
    assert result["low_power"] is True
    assert "LOW POWER" in probe.render(
        {"candidates": ["signal@0h"], "targets": {"event:x": result}, "day_level": {}}
    )
