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
- a fixed seed, so a night's run is reproducible and cannot manufacture significance by retrying,
- enough permutations for the number of candidates examined: Holm multiplies the smallest possible
  p (1 / (1 + B)) by that number, so too few permutations would make an effect impossible rather
  than merely unlikely. B is raised to what is needed and recorded on each finding.

`screen_rates` is the same screen for binary and count targets (an event that is 0 in most hours),
where a median slope is blind: it compares the outcome rate within each hour-of-week between the
top and bottom third of the feature, on the same held-out split, budget, null and correction.

Nothing here reads a database or the lake; callers pass pairs. No cards, no actuation.
"""

import math
import random
from collections import defaultdict
from itertools import combinations

MIN_HOURS = 72
MIN_IMPROVEMENT = 0.10
MAX_PAIRS = 400  # Theil-Sen is O(n^2): subsample evenly beyond this
TRAIN_FRACTION = 0.7

# screen() defaults
MAX_CANDIDATES = 8  # per target; the screen has a fixed budget so it cannot fish
ALPHA = 0.05
PERMUTATIONS = 199
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


def _permutation_p(pairs, observed, permutations, rng, gain_of):
    """Empirical P(gain >= observed) when the feature is circularly shifted against the target.
    The +1 terms keep p > 0 (a finite number of permutations cannot prove p = 0). `pairs` are
    tuples whose first element is the feature; the rest (target, time, ...) stay in place."""
    n = len(pairs)
    xs = [p[0] for p in pairs]
    low = max(1, int(n * MIN_SHIFT_FRACTION))
    high = max(low, n - low)
    hits = 0
    for _ in range(permutations):
        k = rng.randint(low, high)
        shifted = xs[k:] + xs[:k]
        null = [(shifted[i],) + tuple(pairs[i][1:]) for i in range(n)]
        if gain_of(null) >= observed:
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


def _screen(
    candidates,
    *,
    evaluate,
    refit,
    effect_key,
    enough,
    min_improvement,
    max_candidates,
    alpha,
    permutations,
    seed,
):
    """The shared scaffold of `screen` and `screen_rates`: budget, floors, gain bar, permutation
    null, Holm. `evaluate(pairs) -> (effect, gain)`; `refit(pairs) -> effect` on all the data;
    `enough(pairs) -> reason or None` is the sample floor."""
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
        reason = enough(pairs)
        if reason:
            finding.update(status="insufficient_evidence", reason=reason)
            continue
        effect, improvement = evaluate(pairs)
        finding.update({effect_key: round(effect, 6), "improvement": round(improvement, 4)})
        if improvement < min_improvement:
            finding.update(
                status="insufficient_evidence", reason="did not reduce held-out error enough"
            )
            continue
        tested.append((index, pairs, improvement))

    # The permutation null is only run for candidates that already cleared the floor and the gain,
    # but the correction counts every candidate that was looked at, so skipping the null for the
    # obvious misses cannot make the survivors look better than they are.
    # Resolution: with B permutations the smallest possible p is 1 / (1 + B), and Holm multiplies
    # it by the number of candidates looked at. If that product can never get under alpha, an
    # "effect" is impossible however strong the relationship (99 permutations and 8 candidates
    # cannot: 8 / 100 > 0.05). So raise B to what the number of candidates needs, and say so.
    permutations = max(permutations, math.ceil(looked_at / alpha) - 1)
    rng = random.Random(seed)
    raw = [
        _permutation_p(pairs, improvement, permutations, rng, lambda p: evaluate(p)[1])
        for _, pairs, improvement in tested
    ]
    # pad with p = 1 for the candidates that failed earlier so Holm's m is the number looked at
    adjusted = _holm(raw + [1.0] * (looked_at - len(raw)), alpha)
    for slot, (index, pairs, _) in enumerate(tested):
        p_adj, significant = adjusted[slot]
        findings[index].update(p=round(raw[slot], 4), p_adjusted=p_adj, permutations=permutations)
        if significant:
            findings[index].update(
                status="effect",
                reason="beat the shifted-feature null after multiple-testing correction",
            )
            findings[index][effect_key] = round(refit(pairs), 6)
        else:
            findings[index].update(
                status="insufficient_evidence",
                reason="not distinguishable from chance after multiple-testing correction",
            )
    return findings


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
    """Findings for one CONTINUOUS target's candidates: a list of dicts, one per candidate, in the
    order given. Robust slope + median-based held-out gain: right for a series like indoor
    temperature, blind on a mostly-constant target (use `screen_rates` there).

    `candidates`: dicts with `name`, `lag_hours` and `pairs` ((x, y, t) in any order).
    Each finding has `status` in {"effect", "insufficient_evidence", "not_tested"}, `reason`, and
    for tested candidates `n`, `beta`, `improvement`, `p`, `p_adjusted`. A candidate is an
    "effect" only when it clears the sample floor, the minimum held-out gain AND the
    Holm-corrected permutation test across every candidate that was tested. Everything else is
    stored as insufficient evidence, never as a result.
    """
    return _screen(
        candidates,
        evaluate=lambda pairs: held_out_gain(pairs, max_pairs),
        refit=lambda pairs: theil_sen([p[0] for p in pairs], [p[1] for p in pairs], max_pairs),
        effect_key="beta",
        enough=lambda pairs: (
            f"under {min_hours} hours of overlap" if len(pairs) < min_hours else None
        ),
        min_improvement=min_improvement,
        max_candidates=max_candidates,
        alpha=alpha,
        permutations=permutations,
        seed=seed,
    )


# --- Rates: binary and count targets ---------------------------------------------------------
#
# Most of what the household does is rare: an event count that is 0 in most hours, "is this person
# home". A median slope and a median absolute deviation are both 0 on such a target, so `screen`
# sees a gain of exactly 0.0 whatever the relationship (measured on the real lake: 16 of 21 learner
# targets). `screen_rates` asks the question in frequencies instead: within the same hour-of-week,
# is the outcome more (or less) common when the feature is high than when it is low?

RATE_MIN_IMPROVEMENT = 0.01  # of the held-out squared error; the permutation test is the real guard
RATE_MIN_EVENTS = 20  # rows with a non-zero outcome, over the whole overlap


def _bucket(x, lo, hi):
    return 0 if x <= lo else (1 if x <= hi else 2)


def _rate_fit(train):
    """(cell mean by cell, global mean, tercile cut points, mean residual per tercile bucket, rows
    per bucket) from training rows (x, y, t, cell). A binary feature has fewer than three
    populated buckets: the empty ones carry no offset and are skipped when the shift is taken."""
    global_mean = sum(p[1] for p in train) / len(train)
    cells = defaultdict(list)
    for _x, y, _t, cell in train:
        cells[cell].append(y)
    cell_mean = {c: sum(v) / len(v) for c, v in cells.items()}
    xs = sorted(p[0] for p in train)
    lo, hi = xs[len(xs) // 3], xs[(2 * len(xs)) // 3]
    sums, counts = [0.0] * 3, [0] * 3
    for x, y, _t, cell in train:
        b = _bucket(x, lo, hi)
        sums[b] += y - cell_mean[cell]
        counts[b] += 1
    offsets = [sums[b] / counts[b] if counts[b] else 0.0 for b in range(3)]
    return cell_mean, global_mean, (lo, hi), offsets, counts


def held_out_rate_gain(pairs):
    """(rate shift, relative cut in held-out squared error). Rows are (x, y, t, cell) in time
    order. Fitted on the first 70 %: each cell's mean outcome, then the extra rate when the feature
    is in its top vs bottom third. Judged on the final 30 %: how much does adding the feature's
    offset reduce the squared error of the cell-mean prediction? The shift is top minus bottom."""
    cut = int(len(pairs) * TRAIN_FRACTION)
    train, test = pairs[:cut], pairs[cut:]
    cell_mean, global_mean, (lo, hi), offsets, counts = _rate_fit(train)
    before = after = 0.0
    for x, y, _t, cell in test:
        base = cell_mean.get(cell, global_mean)
        before += (y - base) ** 2
        after += (y - base - offsets[_bucket(x, lo, hi)]) ** 2
    return _shift(offsets, counts), (1.0 - after / before if before > 0 else 0.0)


def _shift(offsets, counts):
    """Highest populated bucket's offset minus the lowest populated one's (0.0 if only one)."""
    populated = [b for b in range(3) if counts[b]]
    return offsets[populated[-1]] - offsets[populated[0]] if len(populated) > 1 else 0.0


def rate_effect(pairs):
    """The rate shift (top third minus bottom third of the feature) on ALL rows, once a candidate
    has been validated."""
    _, _, _, offsets, counts = _rate_fit(pairs)
    return _shift(offsets, counts)


def rate_pairs(feature_by_time, rows, lag_hours=0, step=None):
    """(x, y, t, cell) for `rows` of (t, cell, y), pairing each outcome with the feature `lag_hours`
    earlier. `cell` is the structure the learner already models (hour of week); the screen
    compares rates only within a cell's own average."""
    out = []
    for t, cell, y in rows:
        key = t - (step * lag_hours if step is not None else lag_hours)
        x = feature_by_time.get(key)
        if x is not None and y is not None:
            out.append((x, y, t, cell))
    out.sort(key=lambda p: p[2])
    return out


def screen_rates(
    candidates,
    *,
    min_hours=MIN_HOURS,
    min_events=RATE_MIN_EVENTS,
    min_improvement=RATE_MIN_IMPROVEMENT,
    max_candidates=MAX_CANDIDATES,
    alpha=ALPHA,
    permutations=PERMUTATIONS,
    seed=SEED,
):
    """`screen` for binary and count targets. `candidates`: dicts with `name`, `lag_hours` and
    `pairs` ((x, y, t, cell), see `rate_pairs`). Same statuses, budget, shifted-feature null and
    Holm correction; the effect is `rate_shift` (outcome per hour, top third of the feature minus
    bottom third) and a candidate also needs `min_events` non-zero outcomes: a rate cannot be
    estimated from a handful of events, so under that floor the answer is insufficient evidence,
    not a rate."""

    def enough(pairs):
        if len(pairs) < min_hours:
            return f"under {min_hours} hours of overlap"
        events = sum(1 for p in pairs if p[1] != 0)
        if events < min_events:
            return f"only {events} events (need {min_events})"
        return None

    return _screen(
        candidates,
        evaluate=held_out_rate_gain,
        refit=rate_effect,
        effect_key="rate_shift",
        enough=enough,
        min_improvement=min_improvement,
        max_candidates=max_candidates,
        alpha=alpha,
        permutations=permutations,
        seed=seed,
    )
