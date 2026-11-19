"""The nightly discovery screen (Context learning 4/5, todo/sa/todo_lf10_discovery_screen.md).

For every declared target (`sa/targets.py`), every candidate feature and lag from the context
registry, record held-out gain and effect size, or an explicit insufficient-evidence row. This
module computes the rows; storing them (`sa_covariate_findings`) and the API are the next step. It
reads the lake and nothing else: **no cards, no actuation, no model is changed by a finding.**

It cannot manufacture significance:

- a fixed budget (at most `targets.MAX_PER_TARGET` candidate-lags per target, enforced by
  `targets.validate`, which `run_screen` runs first and refuses to go on without);
- the engine's floors (`covariates.MIN_HOURS`; `Target.min_events` for rare outcomes), a held-out
  final 30 %, a shifted-feature permutation null with a fixed seed, and Holm's correction over every
  candidate looked at; no retries and no re-seeding;
- everything under a floor or not distinguishable from chance is stored as `insufficient_evidence`
  with its reason, **never as a result**. Only a candidate that beat the null after correction is
  an `effect`.

Every declared target produces rows on every run: findings, or one explicit row saying why there
are none (no data, a context table missing, the target's declared kind not fitting its data), so a
night's run provably covers the registry.

A target whose outcome is continuous goes to `covariates.screen` on the residual after the
hour-of-week mean; a count or binary one goes to `covariates.screen_rates`, which compares the
outcome's frequency within each hour of week between the top and bottom third of the feature.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import duckdb

from sa import covariates, silver, targets

HOUR = timedelta(hours=1)
ALL = "*"  # feature_key of a row that describes the target as a whole, not one candidate
STATUSES = ("effect", "insufficient_evidence", "not_tested")


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


ANOMALY_DAYS = 7  # the anomaly is measured against this many previous days, same hour of day
ANOMALY_MIN_DAYS = (
    ANOMALY_DAYS  # ... all of them: a partial window leaves a step in a drifting series
)


def anomaly_vs_trailing_week(series):
    """{t: value - mean of the same hour of day over the previous 7 days} for a {t: value} series,
    for hours where all of those days are present (so the first week is dropped). Causal (only the
    past), and local: it removes the daily cycle AND any drift on the scale of weeks, so a feature
    that trends (autumn cooling) cannot pass itself off as a cause of an outcome that also drifts.
    Day to day swings, "warmer than the last week", are what is left."""
    out = {}
    for t, v in series.items():
        if v is None:
            continue
        prior = [
            series[p]
            for p in (t - timedelta(days=d) for d in range(1, ANOMALY_DAYS + 1))
            if series.get(p) is not None
        ]
        if len(prior) >= ANOMALY_MIN_DAYS:
            out[t] = v - sum(prior) / len(prior)
    return out


def _table(lake_dir, layer, table):
    return os.path.exists(os.path.join(lake_dir, layer, table, "part-0.parquet"))


def load_features(con, keys):
    """{feature key: {naive UTC hour: value}} from the long-form gold `context_features` (view
    `g_context_features`), numeric values only. The forecast features are only here, not in
    `context_hourly`."""
    if not keys:
        return {}
    marks = ",".join("?" * len(keys))
    out = {k: {} for k in keys}
    for key, t, value in con.execute(
        f"SELECT feature_key, bucket_utc, value_num FROM g_context_features "
        f"WHERE feature_key IN ({marks}) AND value_num IS NOT NULL",
        list(keys),
    ).fetchall():
        out[key][_naive(t)] = value
    return out


def load_cells(con):
    """{naive UTC hour: (dow_local, hour_local)} from `g_context_hourly`: the hour-of-week cell the
    learners already model."""
    return {
        _naive(t): (dow, hour)
        for t, dow, hour in con.execute(
            "SELECT bucket_utc, dow_local, hour_local FROM g_context_hourly"
        ).fetchall()
    }


def _row(run_date, target, feature, lag, status, reason, now, **fields):
    row = {
        "run_date": run_date,
        "target_key": target.key,
        "feature_key": feature,
        "lag_hours": lag,
        "method": targets.method_for(target),
        "status": status,
        "reason": reason,
        "n": None,
        "effect": None,
        "effect_unit": None,
        "improvement": None,
        "p": None,
        "p_adjusted": None,
        "fitted_from": None,
        "fitted_to": None,
        "evidence": {},
        "computed_at": now,
    }
    row.update(fields)
    return row


def _whole_target_row(run_date, target, reason, now, **fields):
    return _row(run_date, target, ALL, 0, "insufficient_evidence", reason, now, **fields)


def screen_target(target, con, features, cells, run_date, now, permutations):
    """Rows for one target: one per declared candidate-lag, or one row saying why none."""
    rows_raw = [(_naive(t), v) for t, v in targets.values(con, target) if v is not None]
    if not rows_raw:
        return [
            _whole_target_row(run_date, target, "no data: the target has no observed hours", now)
        ]
    values = [v for _, v in rows_raw]
    problem = targets.check_kind(target, values)
    if problem:
        return [_whole_target_row(run_date, target, f"target kind does not fit: {problem}", now)]
    if not cells:
        return [_whole_target_row(run_date, target, "no data: context_hourly is missing", now)]

    placed = [(t, *cells[t], v) for t, v in rows_raw if t in cells]  # (t, dow, hour, y)
    if not placed:
        return [_whole_target_row(run_date, target, "no data: no hour has a context row", now)]
    fitted_from, fitted_to = placed[0][0].date(), placed[-1][0].date()

    slope = target.kind == targets.CONTINUOUS
    if slope:
        residual = residual_by_hour_of_week(placed)
    outcome = [(t, (dow, hour), y) for t, dow, hour, y in placed]

    pairs_list, empty = [], set()
    for feature, lag, transform in targets.expanded(target):
        series = features.get(feature) or {}
        if transform == targets.ANOMALY:
            series = anomaly_vs_trailing_week(series)
        if slope:
            pairs = covariates.lagged_pairs(series, residual, lag_hours=lag, step=HOUR)
        else:
            pairs = covariates.rate_pairs(series, outcome, lag_hours=lag, step=HOUR)
        if not series:
            empty.add((feature, lag))
        pairs_list.append(
            {"name": feature, "lag_hours": lag, "pairs": pairs, "transform": transform}
        )

    if slope:
        findings = covariates.screen(pairs_list, permutations=permutations)
        unit = f"{target.key} per feature unit"
    else:
        findings = covariates.screen_rates(
            pairs_list, min_events=target.min_events, permutations=permutations
        )
        unit = f"{target.key} per hour, top third of the feature minus bottom third"

    out = []
    for cand, f in zip(pairs_list, findings):
        feature, lag = f["name"], f["lag_hours"]
        reason = f.get("reason")
        if (feature, lag) in empty and f["status"] != "not_tested":
            reason = "the feature has no data in the lake yet"
        effect = f.get("beta", f.get("rate_shift"))
        out.append(
            _row(
                run_date,
                target,
                feature,
                lag,
                f["status"],
                reason,
                now,
                n=f.get("n"),
                effect=effect,
                effect_unit=unit if effect is not None else None,
                improvement=f.get("improvement"),
                p=f.get("p"),
                p_adjusted=f.get("p_adjusted"),
                fitted_from=fitted_from,
                fitted_to=fitted_to,
                evidence={
                    "transform": cand["transform"],
                    "kind": target.kind,
                    "cell": "hour of week",
                    "held_out": "final 30 % of the overlap, in time order",
                    "permutations": f.get("permutations", permutations),
                    "alpha": covariates.ALPHA,
                    "seed": covariates.SEED,
                    "min_hours": covariates.MIN_HOURS,
                    **({"min_events": target.min_events} if not slope else {}),
                },
            )
        )
    return out


def run_screen(
    lake_dir,
    run_date=None,
    now=None,
    registry=targets.REGISTRY,
    permutations=covariates.PERMUTATIONS,
):
    """The rows for tonight's findings, one set per declared target. Raises ValueError if the
    target registry is not sound (the screen refuses to run on a registry that could fish)."""
    problems = targets.validate(registry) + targets.validate_queries(registry)
    if problems:
        raise ValueError("target registry is not sound: " + "; ".join(problems))
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    run_date = run_date or now.date()

    if not (
        _table(lake_dir, "gold", "presence_grid")
        and _table(lake_dir, "silver", "presence_intervals")
    ):
        return [
            _whole_target_row(run_date, t, "no data: the presence tables are not built yet", now)
            for t in registry
        ]
    con = duckdb.connect()
    try:
        silver._register_views(con, lake_dir)
        keys = sorted({c.feature for t in registry for c in t.candidates})
        features = load_features(con, keys) if _table(lake_dir, "gold", "context_features") else {}
        cells = load_cells(con) if _table(lake_dir, "gold", "context_hourly") else {}
        rows = []
        for t in registry:
            rows.extend(screen_target(t, con, features, cells, run_date, now, permutations))
        return rows
    finally:
        con.close()


RETENTION_DAYS = 90  # nightly findings kept (the same value is in migration 057's comment)

_COLUMNS = (
    "run_date, target_key, feature_key, lag_hours, method, status, reason, n, effect, "
    "effect_unit, improvement, p, p_adjusted, fitted_from, fitted_to, evidence, computed_at"
)


def _db_row(r):
    import json

    return (
        r["run_date"],
        r["target_key"],
        r["feature_key"],
        r["lag_hours"],
        r["method"],
        r["status"],
        (r["reason"] or "")[:255] or None,
        r["n"],
        r["effect"],
        r["effect_unit"],
        r["improvement"],
        r["p"],
        r["p_adjusted"],
        r["fitted_from"],
        r["fitted_to"],
        json.dumps(r["evidence"], default=str),
        r["computed_at"],
    )


def store(conn, rows, retention_days=RETENTION_DAYS):
    """Write tonight's rows to `sa_covariate_findings` in one transaction: a re-run of the same
    night replaces that night's rows, and runs older than the retention are pruned. Returns the
    number of rows written. Rolls back and re-raises on any error."""
    if not rows:
        return 0
    run_date = rows[0]["run_date"]
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM sa_covariate_findings WHERE run_date = %s", (run_date,))
        marks = ", ".join(["%s"] * 17)
        cursor.executemany(
            f"INSERT INTO sa_covariate_findings ({_COLUMNS}) VALUES ({marks})",
            [_db_row(r) for r in rows],
        )
        cursor.execute(
            "DELETE FROM sa_covariate_findings WHERE run_date < %s",
            (run_date - timedelta(days=retention_days),),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def run(lake_dir, conn, **kwargs):
    """Screen the lake and store the findings. Called by sa-learner after the learners; returns
    {"rows": n, "summary": {...}}."""
    rows = run_screen(lake_dir, **kwargs)
    return {"rows": store(conn, rows), "summary": summarize(rows)}


def summarize(rows):
    """{target: {"effects": n, "insufficient_evidence": n, "not_tested": n}} for logging."""
    out = {}
    for r in rows:
        counts = out.setdefault(
            r["target_key"], {"effect": 0, "insufficient_evidence": 0, "not_tested": 0}
        )
        counts[r["status"]] += 1
    return out
