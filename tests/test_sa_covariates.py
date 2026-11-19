"""The shared covariate engine (sa/covariates.py, Context learning 3/5).

Three groups: parity with the scalar learner's original test (a verbatim copy of the old code is the
reference, so the refactor cannot change a fitted profile), the many-candidate screen's honesty
(a planted relationship is found, a planted null is not, the budget and floors hold), and the small
statistics.
"""

import random
from datetime import datetime, timedelta
from itertools import combinations

import pytest

from services.service_sa.sa import covariates
from services.service_sa.sa.learners import scalar

T0 = datetime(2026, 11, 1)


# --- the scalar learner's ORIGINAL code, copied verbatim, as the parity reference ----------------


def _old_theil_sen(xs, ys):
    n = len(xs)
    if n > scalar.COVARIATE_MAX_PAIRS:
        step = n / scalar.COVARIATE_MAX_PAIRS
        picks = [int(i * step) for i in range(scalar.COVARIATE_MAX_PAIRS)]
        xs, ys = [xs[i] for i in picks], [ys[i] for i in picks]
    slopes = [
        (y2 - y1) / (x2 - x1)
        for (x1, y1), (x2, y2) in combinations(zip(xs, ys), 2)
        if abs(x2 - x1) > 1e-9
    ]
    if not slopes:
        return 0.0
    slopes.sort()
    return slopes[len(slopes) // 2]


def _old_select_covariate(residuals, name):
    pairs = [(x["c"], x["r"], x["t"]) for x in residuals if x["c"] is not None]
    detail = {"name": name, "overlap_hours": len(pairs), "used": False}
    if len(pairs) < scalar.MIN_COVARIATE_HOURS:
        detail["note"] = f"under {scalar.MIN_COVARIATE_HOURS} hours of overlap"
        return None, detail
    pairs.sort(key=lambda p: p[2])
    cut = int(len(pairs) * 0.7)
    train, test = pairs[:cut], pairs[cut:]
    beta = _old_theil_sen([c for c, _, _ in train], [r for _, r, _ in train])

    def mad(values):
        centre = scalar.weighted_median(values, [1.0] * len(values))
        return scalar.weighted_median([abs(v - centre) for v in values], [1.0] * len(values))

    before = mad([r for _, r, _ in test])
    after = mad([r - beta * c for c, r, _ in test])
    improvement = 1.0 - after / before if before > 0 else 0.0
    detail.update({"beta": beta, "improvement": round(improvement, 4)})
    if improvement < scalar.COVARIATE_MIN_IMPROVEMENT:
        detail["note"] = "did not reduce held-out error enough"
        return None, detail
    detail["used"] = True
    return _old_theil_sen([c for c, _, _ in pairs], [r for _, r, _ in pairs]), detail


def _residuals(n, slope, noise, seed, none_every=0):
    rng = random.Random(seed)
    out, x = [], 0.0
    for i in range(n):
        x += rng.gauss(0, 1)
        c = None if none_every and i % none_every == 0 else x
        r = slope * (x if c is not None else 0.0) + rng.gauss(0, noise)
        out.append({"t": T0 + timedelta(hours=i), "r": r, "w": 1.0, "c": c})
    rng.shuffle(out)  # the selector must sort by time itself
    return out


class TestScalarParity:
    @pytest.mark.parametrize(
        "n,slope,noise,none_every",
        [
            (30, 1.0, 0.5, 0),  # under the floor
            (200, 0.0, 1.0, 0),  # nothing there
            (200, 1.5, 0.5, 0),  # a strong relationship
            (500, 0.3, 1.0, 7),  # past MAX_PAIRS, with gaps in the covariate
            (150, 0.05, 2.0, 0),  # a weak one near the gain threshold
        ],
    )
    def test_select_matches_the_original_exactly(self, n, slope, noise, none_every):
        for seed in range(5):
            residuals = _residuals(n, slope, noise, seed, none_every)
            assert scalar._select_covariate(residuals, "outdoor_temp_c") == _old_select_covariate(
                residuals, "outdoor_temp_c"
            )

    def test_theil_sen_matches_the_original(self):
        rng = random.Random(3)
        for n in (10, 80, 399, 400, 401, 900):
            xs = [rng.uniform(-5, 5) for _ in range(n)]
            ys = [2 * x + rng.gauss(0, 1) for x in xs]
            assert scalar.theil_sen(xs, ys) == _old_theil_sen(xs, ys)

    def test_fit_points_records_the_covariate_evidence_without_changing_the_rest(self):
        pts = []
        rng = random.Random(1)
        cov = []
        x = 0.0
        for i in range(24 * 14):
            t = T0 + timedelta(hours=i)
            x += rng.gauss(0, 0.3)
            cov.append({"t": t, "value": 10 + x})
            pts.append(
                {
                    "t": t,
                    "date": t.date(),
                    "hour": t.hour,
                    "value": 20 + 0.8 * x + rng.gauss(0, 0.2),
                    "coverage": 1.0,
                }
            )
        ref = pts[-1]["date"]
        profile = scalar.fit_points("s", pts, ref, covariate=cov)
        assert profile.params["covariates"] == [profile.params["covariate"]]
        assert profile.params["covariate"]["name"] == "outdoor_temp_c"
        bare = scalar.fit_points("s", pts, ref)
        assert bare.params["covariates"] == []


class TestStatistics:
    def test_weighted_median_and_mad(self):
        assert covariates.weighted_median([1, 2, 3], [1, 1, 1]) == 2
        assert covariates.weighted_median([], []) is None
        assert covariates.mad([1, 2, 3, 4, 100]) == 1

    def test_theil_sen_ignores_outliers(self):
        xs = list(range(20))
        ys = [2 * x for x in xs]
        ys[3], ys[15] = 500, -400
        assert covariates.theil_sen(xs, ys) == pytest.approx(2, abs=0.05)

    def test_lagged_pairs_use_the_earlier_feature(self):
        step = timedelta(hours=1)
        feature = {T0 + step * i: float(i) for i in range(10)}
        target = {T0 + step * i: float(i) * 10 for i in range(10)}
        pairs = covariates.lagged_pairs(feature, target, lag_hours=3, step=step)
        assert pairs[0][:2] == (0.0, 30.0)  # target at hour 3 pairs with the feature at hour 0
        assert len(pairs) == 7
        assert covariates.lagged_pairs(feature, target, lag_hours=0, step=step)[0][:2] == (0.0, 0.0)

    def test_holm_is_monotone_and_conservative(self):
        out = covariates._holm([0.01, 0.04, 0.03], 0.05)
        assert out[0] == (0.03, True)  # 3 * 0.01
        assert out[2] == (0.06, False)  # 2 * 0.03 = 0.06 > 0.05, and nothing after it passes
        assert out[1][1] is False and out[1][0] >= out[2][0]


def _pairs(n, seed, slope=0.0, noise=1.0):
    rng = random.Random(seed)
    out, x = [], 0.0
    for i in range(n):
        x += rng.gauss(0, 1)  # autocorrelated, like weather
        out.append((x, slope * x + rng.gauss(0, noise), T0 + timedelta(hours=i)))
    return out


FAST = dict(permutations=49, min_hours=72)


class TestScreen:
    def test_a_planted_relationship_is_found(self):
        findings = covariates.screen(
            [{"name": "signal", "lag_hours": 0, "pairs": _pairs(240, 1, slope=1.0)}], **FAST
        )
        assert findings[0]["status"] == "effect"
        assert findings[0]["beta"] == pytest.approx(1.0, abs=0.2)
        assert findings[0]["p_adjusted"] <= 0.05

    def test_a_planted_null_is_not(self):
        for seed in range(6):
            findings = covariates.screen(
                [{"name": "noise", "lag_hours": 0, "pairs": _pairs(240, seed)}], **FAST
            )
            assert findings[0]["status"] == "insufficient_evidence", seed

    def test_many_null_candidates_do_not_manufacture_an_effect(self):
        # Eight independent nulls against one target: uncorrected, a 10 % gain bar on a shared
        # held-out window would let some through; corrected, none should.
        base = _pairs(240, 99)
        candidates = []
        for k in range(8):
            xs = [x for x, _, _ in _pairs(240, 1000 + k)]
            candidates.append(
                {
                    "name": f"null{k}",
                    "lag_hours": k,
                    "pairs": [(xs[i], base[i][1], base[i][2]) for i in range(240)],
                }
            )
        findings = covariates.screen(candidates, **FAST)
        assert [f["status"] for f in findings].count("effect") == 0

    def test_the_real_candidate_survives_among_nulls(self):
        base = _pairs(240, 5, slope=1.0)
        noise = [x for x, _, _ in _pairs(240, 77)]
        candidates = [
            {"name": "real", "lag_hours": 0, "pairs": base},
            {
                "name": "decoy",
                "lag_hours": 1,
                "pairs": [(noise[i], base[i][1], base[i][2]) for i in range(240)],
            },
        ]
        by_name = {f["name"]: f for f in covariates.screen(candidates, **FAST)}
        assert by_name["real"]["status"] == "effect"
        assert by_name["decoy"]["status"] == "insufficient_evidence"

    def test_the_sample_floor_and_the_budget_are_enforced(self):
        short = {"name": "short", "lag_hours": 0, "pairs": _pairs(30, 1, slope=1.0)}
        findings = covariates.screen([short], **FAST)
        assert findings[0]["status"] == "insufficient_evidence"
        assert "under 72 hours" in findings[0]["reason"]

        many = [{"name": f"c{k}", "lag_hours": k, "pairs": _pairs(100, k)} for k in range(5)]
        findings = covariates.screen(many, max_candidates=3, permutations=9, min_hours=72)
        assert [f["status"] == "not_tested" for f in findings] == [False] * 3 + [True] * 2
        assert "budget of 3" in findings[3]["reason"]

    def test_it_is_reproducible(self):
        cands = [{"name": "s", "lag_hours": 0, "pairs": _pairs(200, 4, slope=0.4, noise=1.0)}]
        assert covariates.screen(cands, **FAST) == covariates.screen(cands, **FAST)
