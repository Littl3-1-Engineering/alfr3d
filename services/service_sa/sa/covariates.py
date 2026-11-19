"""Shared covariate engine (Context learning 3/5, todo/sa/todo_lf9_covariate_engine.md).

One place that answers "does this context signal explain any of what this learner sees, beyond
chance?" for any learner and any signal, so a relationship is found by registering a signal, not by
writing code. Extracted from the scalar learner (LF-4a), where it first appeared; the scalar learner
now calls it and its fitted profiles are unchanged (tests/test_sa_covariates.py proves it).

The method is deliberately small and explainable:

- **Effect size**: a Theil-Sen slope (the median of all pairwise slopes), so outliers (a speed test
  reporting 1,800,000 ms) do not move it.
- **Held-out gain**: pairs are put in time order, the slope is fitted on the first 70 % and judged
  on the final 30 %: how much did subtracting beta * x cut the median absolute deviation of y?
  Never a fit judged on itself.
- **Honest small n** (one household): a sample floor, a minimum gain, and an explicit
  "insufficient evidence" outcome that is stored as such, never as a result.

`select` is the single-candidate test the scalar learner always used (kept exactly). `screen` is
the many-candidate version for discovery: candidate features x lags against one target, with

- a **cap** on candidates per target (the rest are listed as not tested, never silently dropped),
- **multiple-testing control**: a circular-shift permutation null (the feature is shifted against
  the target, which keeps its autocorrelation and destroys any real alignment) gives each candidate
  an empirical p-value, and Holm's step-down correction is applied across the candidates tested,
- a fixed seed, so a night's run is reproducible and cannot manufacture significance by retrying.

Nothing here reads a database or the lake; callers pass pairs. No cards, no actuation.
"""

import random
from itertools import combinations

MIN_HOURS = 72
MIN_IMPROVEMENT = 0.10
MAX_PAIRS = 400  # Theil-Sen is O(n^2): subsample evenly beyond this
TRAIN_FRACTION = 0.7

# screen() defaults
MAX_CANDIDATES = 8  # per target; the screen has a fixed budget so it cannot fish
ALPHA = 0.05
PERMUTATIONS = 99
SCREEN_MAX_PAIRS = 150  # smaller than MAX_PAIRS: it runs once per permutation
MIN_SHIFT_FRACTION = 0.1  # a permutation shifts at least this far, so it is not the identity
SEED = 20261118


def weighted_median(values, weights):
    """Median where each value carries a weight; None for no data."""
    pairs = sorted((v, w) for v, w in zip(values, weights) if w > 0)
    if not pairs:
        return None
    half = sum(w for _, w in pairs) / 2.0
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= half:
            return value
    return pairs[-1][0]


def mad(values):
    """Median absolute deviation (unweighted)."""
    centre = weighted_median(values, [1.0] * len(values))
    return weighted_median([abs(v - centre) for v in values], [1.0] * len(values))


def theil_sen(xs, ys, max_pairs=MAX_PAIRS):
    """Robust slope: the median of all pairwise slopes. Evenly subsampled beyond `max_pairs`
    points so the cost stays bounded."""
    n = len(xs)
    if n > max_pairs:
        step = n / max_pairs
        picks = [int(i * step) for i in range(max_pairs)]
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


def held_out_gain(pairs, max_pairs=MAX_PAIRS):
    """(beta fitted on the first 70 %, relative cut in the final 30 %'s MAD). `pairs` are
    (x, y, t) already in time order. The gain is 0.0 when the held-out MAD is zero."""
    cut = int(len(pairs) * TRAIN_FRACTION)
    train, test = pairs[:cut], pairs[cut:]
    beta = theil_sen([x for x, _, _ in train], [y for _, y, _ in train], max_pairs)
    before = mad([y for _, y, _ in test])
    after = mad([y - beta * x for x, y, _ in test])
    return beta, (1.0 - after / before if before > 0 else 0.0)


def select(
    pairs,
    name,
    min_hours=MIN_HOURS,
    min_improvement=MIN_IMPROVEMENT,
    max_pairs=MAX_PAIRS,
):
    """(beta, detail) if the covariate earns its place on a held-out final 30 %, else (None,
    detail). One candidate, no multiple-testing correction: this is the scalar learner's test,
    unchanged. `pairs`: (x, y, t) in any order."""
    detail = {"name": name, "overlap_hours": len(pairs), "used": False}
    if len(pairs) < min_hours:
        detail["note"] = f"under {min_hours} hours of overlap"
        return None, detail
    pairs = sorted(pairs, key=lambda p: p[2])
    beta, improvement = held_out_gain(pairs, max_pairs)
    detail.update({"beta": beta, "improvement": round(improvement, 4)})
    if improvement < min_improvement:
        detail["note"] = "did not reduce held-out error enough"
        return None, detail
    detail["used"] = True
    # Refit the slope on all the data now that it has been validated.
    return theil_sen([x for x, _, _ in pairs], [y for _, y, _ in pairs], max_pairs), detail


def lagged_pairs(feature_by_time, target_by_time, lag_hours=0, step=None):
    """(x, y, t) for every time t where the target exists and the feature existed `lag_hours`
    earlier (a positive lag means the feature leads). `step` is the timedelta of one hour; pass
    `timedelta(hours=1)` for datetime keys, leave None for integer-hour keys."""
    out = []
    for t, y in target_by_time.items():
        key = t - (step * lag_hours if step is not None else lag_hours)
        x = feature_by_time.get(key)
        if x is not None and y is not None:
            out.append((x, y, t))
    out.sort(key=lambda p: p[2])
    return out


def _permutation_p(pairs, observed, permutations, rng, max_pairs):
    """Empirical P(gain >= observed) when the feature is circularly shifted against the target.
    The +1 terms keep p > 0 (a finite number of permutations cannot prove p = 0)."""
    n = len(pairs)
    xs = [x for x, _, _ in pairs]
    low = max(1, int(n * MIN_SHIFT_FRACTION))
    high = max(low, n - low)
    hits = 0
    for _ in range(permutations):
        k = rng.randint(low, high)
        shifted = xs[k:] + xs[:k]
        null = [(shifted[i], pairs[i][1], pairs[i][2]) for i in range(n)]
        if held_out_gain(null, max_pairs)[1] >= observed:
            hits += 1
    return (1 + hits) / (1 + permutations)


def _holm(p_values, alpha):
    """Holm step-down: {index: (adjusted p, significant)} for a list of raw p-values."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    m = len(p_values)
    out, running, rejecting = {}, 0.0, True
    for rank, i in enumerate(order):
        adjusted = min(1.0, (m - rank) * p_values[i])
        running = max(running, adjusted)  # adjusted p-values must not decrease down the order
        rejecting = rejecting and running <= alpha
        out[i] = (round(running, 4), rejecting)
    return out


def screen(
    candidates,
    *,
    min_hours=MIN_HOURS,
    min_improvement=MIN_IMPROVEMENT,
    max_candidates=MAX_CANDIDATES,
    alpha=ALPHA,
    permutations=PERMUTATIONS,
    max_pairs=SCREEN_MAX_PAIRS,
    seed=SEED,
):
    """Findings for one target's candidates: a list of dicts, one per candidate, in the order given.

    `candidates`: dicts with `name`, `lag_hours` and `pairs` ((x, y, t) in any order).
    Each finding has `status` in {"effect", "insufficient_evidence", "not_tested"}, `reason`, and
    for tested candidates `n`, `beta`, `improvement`, `p`, `p_adjusted`. A candidate is an
    "effect" only when it clears the sample floor, the minimum held-out gain AND the
    Holm-corrected permutation test across every candidate that was tested. Everything else is
    stored as insufficient evidence, never as a result.
    """
    findings = [
        {"name": c["name"], "lag_hours": c.get("lag_hours", 0), "status": "not_tested"}
        for c in candidates
    ]
    tested, looked_at = [], 0
    for index, cand in enumerate(candidates):
        if looked_at >= max_candidates:
            findings[index]["reason"] = f"over the budget of {max_candidates} candidates per target"
            continue
        looked_at += 1  # the budget counts every candidate examined, not only the survivors
        pairs = sorted(cand["pairs"], key=lambda p: p[2])
        finding = findings[index]
        finding["n"] = len(pairs)
        if len(pairs) < min_hours:
            finding.update(
                status="insufficient_evidence", reason=f"under {min_hours} hours of overlap"
            )
            continue
        beta, improvement = held_out_gain(pairs, max_pairs)
        finding.update(beta=round(beta, 6), improvement=round(improvement, 4))
        if improvement < min_improvement:
            finding.update(
                status="insufficient_evidence", reason="did not reduce held-out error enough"
            )
            continue
        tested.append((index, pairs, improvement))

    # The permutation null is only run for candidates that already cleared the floor and the gain,
    # but the correction counts every candidate that was looked at, so skipping the null for the
    # obvious misses cannot make the survivors look better than they are.
    rng = random.Random(seed)
    raw = []
    for index, pairs, improvement in tested:
        raw.append(_permutation_p(pairs, improvement, permutations, rng, max_pairs))
    # pad with p = 1 for the candidates that failed earlier so Holm's m is the number looked at
    padded = raw + [1.0] * (looked_at - len(raw))
    adjusted = _holm(padded, alpha)
    for slot, (index, pairs, _) in enumerate(tested):
        p_adj, significant = adjusted[slot]
        findings[index].update(p=round(raw[slot], 4), p_adjusted=p_adj)
        if significant:
            findings[index].update(
                status="effect",
                reason="beat the shifted-feature null after multiple-testing correction",
                beta=round(
                    theil_sen([x for x, _, _ in pairs], [y for _, y, _ in pairs], max_pairs), 6
                ),
            )
        else:
            findings[index].update(
                status="insufficient_evidence",
                reason="not distinguishable from chance after multiple-testing correction",
            )
    return findings
