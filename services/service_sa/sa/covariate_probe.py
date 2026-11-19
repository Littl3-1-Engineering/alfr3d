"""Covariate probe: does any registered context signal explain what a learner's own model leaves
over? (Context learning 3/5, step 2; todo/sa/todo_lf9_covariate_engine.md.)

Phase 3 lets a learner opt in to a covariate only "where Phase 1's replay shows held-out gain".
This is the cheap first look that decides which learners are worth an opt-in PR at all. It is
read-only against the lake, produces a report, changes nothing and registers nothing.

For each target it takes the residual after the hour-of-week structure every learner already
models (the target minus its own mean for that day-of-week and hour), pairs it with each candidate
feature (and lag) from `context_hourly`, and runs `covariates.screen`: a time-blocked held-out gain,
a sample floor, a candidate budget, and a Holm-corrected circular-shift permutation test. A
relationship counts only as `effect`; everything else is `insufficient_evidence`, with the reason.

Sparse targets (an event count that is zero in most hours, "is this person home" for someone who
rarely is) cannot be screened by a median slope, so they go to `covariates.screen_rates`, which
compares the outcome's frequency within each hour of week between the top and bottom third of the
feature. The report says which method each target used.

This is a PROXY for each learner's own residuals, not a replacement for them: a learner whose real
model differs (the presence profile's recency weighting, the rate learner's day types) can behave
differently, so an `effect` here earns an opt-in PR with its own replay before/after, and an
`insufficient_evidence` here is a reason to leave that learner alone, not proof of no relationship.

Day-level learners (stay, daytime, household day) have one observation per day or episode, far
under the engine's sample floor with about two months of history; the probe says so with the counts
instead of pretending to test them.

    python -m sa.covariate_probe [--lake DIR] [--permutations N] [--json]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import timedelta

import duckdb

HOUR = timedelta(hours=1)

# (key in context_hourly, lags in hours, take the anomaly vs its own hour-of-day mean). The
# anomaly is used for the weather series because the hour-of-week structure is already removed from
# the target; raw temperature would only re-find the daily cycle. Calendar busy minutes and the
# forecast probability are used raw. Eight candidates is the engine's per-target budget.
CANDIDATES = (
    ("outdoor_temp_c", 0, True),
    ("outdoor_temp_c", 3, True),
    ("outdoor_humidity_pct", 0, True),
    ("outdoor_pressure_hpa", 0, True),
    ("calendar_busy_minutes", 0, False),
    ("calendar_busy_minutes", 1, False),
    ("forecast_rain_probability", 0, False),
    ("forecast_temp_c", 0, True),
)

# A target at least this often exactly zero is screened by frequency, not by median slope: the
# slope and the MAD are both 0 on it (measured on the real lake), so the slope screen sees nothing.
SPARSE_ZERO_SHARE = 0.5

DAY_LEVEL_LEARNERS = ("stay", "daytime", "household_day")


def _path(lake_dir, layer, table):
    return os.path.join(lake_dir, layer, table, "part-0.parquet")


def _naive(t):
    return t.replace(tzinfo=None) if getattr(t, "tzinfo", None) else t


def residual_by_hour_of_week(rows):
    """{t: y - mean(y | dow, hour)} for `rows` of (t, dow, hour, y). In-sample on purpose: it only
    removes the structure every learner already models."""
    cells = defaultdict(list)
    for _t, dow, hour, y in rows:
        cells[(dow, hour)].append(y)
    mean = {k: sum(v) / len(v) for k, v in cells.items()}
    return {t: y - mean[(dow, hour)] for t, dow, hour, y in rows}


def anomaly_by_hour_of_day(series):
    """{t: value - that hour of day's mean} for a {t: value} series (None values dropped)."""
    cells = defaultdict(list)
    for t, v in series.items():
        if v is not None:
            cells[t.hour].append(v)
    mean = {h: sum(v) / len(v) for h, v in cells.items()}
    return {t: v - mean[t.hour] for t, v in series.items() if v is not None}


def load_features(lake_dir):
    """{feature key: {naive UTC hour: value}} for the probe's candidate keys (context_hourly)."""
    path = _path(lake_dir, "gold", "context_hourly")
    if not os.path.exists(path):
        return {}
    keys = sorted({k for k, _, _ in CANDIDATES})
    con = duckdb.connect()
    try:
        have = {
            r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
        }
        keys = [k for k in keys if k in have]
        if not keys:
            return {}
        rows = con.execute(
            f"SELECT bucket_utc, {', '.join(keys)} FROM read_parquet('{path}') ORDER BY bucket_utc"
        ).fetchall()
    finally:
        con.close()
    return {k: {_naive(r[0]): r[1 + i] for r in rows} for i, k in enumerate(keys)}


def load_presence_targets(lake_dir):
    """{user: [(t, dow, hour, home fraction)]} for observed hours, from the gold presence grid."""
    path = _path(lake_dir, "gold", "presence_grid")
    if not os.path.exists(path):
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT username, bucket_utc, dow_local, hour_local, minutes_home "
            f"FROM read_parquet('{path}') WHERE observed ORDER BY username, bucket_utc"
        ).fetchall()
    finally:
        con.close()
    out = defaultdict(list)
    for name, t, dow, hour, minutes in rows:
        out[f"presence:{name}"].append((_naive(t), dow, hour, minutes / 60.0))
    return out


def load_rate_targets(lake_dir):
    """{stream: [(t, dow, hour, count)]}, zero-filled hourly, from the rate learner's own loader
    so the probe sees exactly the series that learner is fitted on."""
    from sa.learners import rates

    streams = rates.load_streams(lake_dir).get("streams", {})
    out = {}
    for key, stream in streams.items():
        rows = [
            (_naive(p["t"]), p["date"].weekday(), p["hour"], float(p["n"]))
            for p in stream["points"]
            if p["t"] is not None  # a local hour that does not exist (DST gap) has no UTC time
        ]
        if rows:
            out[key] = rows
    return out


def candidate_series(features):
    """[(name, lag, {t: x})] for the candidates the lake can supply."""
    out = []
    for key, lag, anomaly in CANDIDATES:
        series = features.get(key)
        if not series or all(v is None for v in series.values()):
            continue
        out.append((key + ("_anomaly" if anomaly else ""), lag, anomaly_or_raw(series, anomaly)))
    return out


def anomaly_or_raw(series, anomaly):
    return (
        anomaly_by_hour_of_day(series)
        if anomaly
        else {t: v for t, v in series.items() if v is not None}
    )


def probe_target(rows, cands, **screen_kwargs):
    """Screen one target. A sparse target (most hours zero) goes to `screen_rates`, which compares
    the outcome's frequency within each hour of week; a dense one goes to the robust-slope
    `screen` on its residual. `method` says which, because the two are not comparable."""
    from sa import covariates

    zero_share = sum(1 for *_, y in rows if y == 0) / len(rows) if rows else 0.0
    sparse = zero_share >= SPARSE_ZERO_SHARE
    if sparse:
        outcome = [(t, (dow, hour), y) for t, dow, hour, y in rows]
        candidates = [
            {
                "name": name,
                "lag_hours": lag,
                "pairs": covariates.rate_pairs(series, outcome, lag_hours=lag, step=HOUR),
            }
            for name, lag, series in cands
        ]
        findings = covariates.screen_rates(candidates, **screen_kwargs)
    else:
        residual = residual_by_hour_of_week(rows)
        candidates = [
            {
                "name": name,
                "lag_hours": lag,
                "pairs": covariates.lagged_pairs(series, residual, lag_hours=lag, step=HOUR),
            }
            for name, lag, series in cands
        ]
        findings = covariates.screen(candidates, **screen_kwargs)
    return {
        "n": len(rows),
        "zero_share": round(zero_share, 3),
        "method": "rates" if sparse else "slope",
        "findings": findings,
    }


def report(lake_dir, **screen_kwargs):
    features = load_features(lake_dir)
    cands = candidate_series(features)
    targets = {}
    for loader in (load_presence_targets, load_rate_targets):
        for name, rows in loader(lake_dir).items():
            targets[name] = probe_target(rows, cands, **screen_kwargs)
    days = len({t.date() for rows in load_presence_targets(lake_dir).values() for t, *_ in rows})
    return {
        "lake": lake_dir,
        "candidates": [f"{n}@{lag}h" for n, lag, _ in cands],
        "targets": targets,
        "day_level": {
            name: {"observations_per_day": 1, "days_of_history": days}
            for name in DAY_LEVEL_LEARNERS
        },
        "note": "residual after the hour-of-week mean; a proxy for each learner's own residuals",
    }


def render(rep):
    lines = [f"candidates: {', '.join(rep['candidates'])}", ""]
    for name, t in sorted(rep["targets"].items()):
        effects = [f for f in t["findings"] if f["status"] == "effect"]
        lines.append(
            f"{name}  (n={t['n']}, {t['zero_share']:.0%} zero, {t['method']})  "
            f"effects: {len(effects)}"
        )
        for f in t["findings"]:
            effect = f.get("rate_shift", f.get("beta"))
            lines.append(
                f"    {f['name']}@{f['lag_hours']}h  {f['status']}"
                + (f"  gain={f['improvement']}" if "improvement" in f else "")
                + (f"  effect={effect}" if f["status"] == "effect" else "")
                + (f"  p_adj={f['p_adjusted']}" if "p_adjusted" in f else "")
                + (f"  [{f['reason']}]" if f["status"] != "effect" and "reason" in f else "")
            )
    lines.append("")
    for name, d in rep["day_level"].items():
        lines.append(f"{name}: day-level, {d['days_of_history']} days of history: not testable yet")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lake", default=None)
    parser.add_argument("--permutations", type=int, default=99)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    from sa import lake

    rep = report(args.lake or lake.LAKE_DIR, permutations=args.permutations)
    print(json.dumps(rep, indent=1, default=str) if args.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
