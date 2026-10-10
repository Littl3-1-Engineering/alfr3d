"""Scalar-series learner: is this reading unusual for this series, right now? (LF-4a,
todo/sa/todo_signal_inventory.md.) The second learner family; presence (LF-3) was the first.

It serves every numeric series in the gold `scalar_hourly` table: indoor temperature and humidity,
Wi-Fi signal, the phone's battery, network speed tests, and whatever is added next. The legacy
SA-9 rule it shadows (`climate_deviation`) compares a reading with a static median +/- 2 sigma band
per time-of-day bucket. That cannot separate a sudden change from a slow drift, and the data say
which matters: on the household's indoor temperature the day-to-day swing (daily means 23.7 to
26.6 C) is as large as the daily cycle (25.0 to 26.1 C).

Model
-----
For a series y observed hourly, expected value at hour t is

    mu_t = L_t + e[hour_of_day(t)] (+ beta * c_t when a covariate has earned its place)

- e[h]   the hour effect: typical deviation of hour h from its own day's mean, a recency-weighted
         median over days (half-life HALF_LIFE_DAYS), centred on zero.
- L_t    the local level: a lag-weighted mean (half-life LEVEL_HALF_LIFE_HOURS) of the previous 24
         hours *after removing their hour effects*. It follows slow drift (weather, heating) and so
         the model asks "is this hour odd given the last day", not "is it odd for 3 a.m.".
- sigma  1.4826 x the weighted median absolute deviation of the one-step-ahead residuals. Median-
         based on purpose: a speed test reporting a 1,800,000 ms ping, or a sensor reading zero on a
         failed fetch, must not inflate the scale and hide the next real anomaly.

Residuals use only data before each hour, so sigma is an honest forecast error, not a fit to itself.

A deviation is z = (y - mu) / sigma with a two-sided normal tail probability, surprise in bits, and
the shared confidence (sa/confidence.py). The normal tail is an approximation, so the flag threshold
MIN_ABS_Z was chosen from the backtest's actual false-alarm rate, not read off a table.

Covariates ("unusual for the weather")
--------------------------------------
Pass a covariate (e.g. outdoor temperature) and the learner measures its anomaly (value minus its
trailing-24 h level), fits a robust Theil-Sen slope against the series' residuals, and keeps it only
if it cuts the residual MAD by COVARIATE_MIN_IMPROVEMENT on a held-out final 30 %. With under
MIN_COVARIATE_HOURS of overlap, or no gain, it stays off and says so in the profile. Today it stays
off: outdoor weather in the right place has existed for a day.

What this learner does not do
-----------------------------
It scores values, not behaviour over days: weekday vs weekend, seasons, and anything slower than the
24 h level need more history than exists (about three weeks). `sufficiency` says so.
"""

import logging
import math
import sys
from datetime import datetime, timedelta
from itertools import combinations

import duckdb

from sa import confidence, inference_store
from sa.learners.base import Inference, Learner, Profile, utcnow

logger = logging.getLogger("SAScalar")

NAME = "scalar_baseline"
VERSION = "1"
SIGNAL = "scalar.value"

# --- Model ---------------------------------------------------------------------------------
HALF_LIFE_DAYS = 14.0
LEVEL_HOURS = 24
LEVEL_HALF_LIFE_HOURS = 6.0
MIN_LEVEL_POINTS = 6  # of the previous 24 hours must be present to form a level at all
MIN_HOURS_TO_FIT = 72
MIN_COVERAGE = 0.5  # an hour with less than this fraction of readings is not an observation
SIGMA_FLOOR_FRACTION = 0.02  # of the series' p10-p90 spread, so a flat series can't get sigma ~ 0
MIN_DAY_POINTS = 12  # hours needed in a local day for it to define a day mean

# --- Covariate -----------------------------------------------------------------------------
MIN_COVARIATE_HOURS = 72
COVARIATE_MIN_IMPROVEMENT = 0.10
COVARIATE_MAX_PAIRS = 400  # Theil-Sen is O(n^2): subsample evenly beyond this

# --- Confidence terms ----------------------------------------------------------------------
RECENT_HOURS = 168
STABILITY_RECENT_DAYS = 7
STABILITY_PRIOR_DAYS = 14
STABILITY_UNKNOWN = 0.5
MIN_STABILITY_RESIDUALS = 24
QUALITY_FLOOR = 0.3

# --- Scoring -------------------------------------------------------------------------------
# Chosen from the backtest on the household's indoor climate (see todo_lf4_port_baselines.md): the
# smallest threshold that keeps flagged hours to a handful a week per series.
MIN_ABS_Z = 4.0


# Count-like series (switches and unlocks per report) are spiky and right-skewed: the natural
# scale for "unusual" is a multiple, not a difference, so they are modelled as log(1 + value).
LOG_SERIES_PREFIXES = ("attention:",)


def uses_log(series_key):
    return series_key.startswith(LOG_SERIES_PREFIXES)


def to_model(series_key, value):
    """A raw reading on the scale the series is modelled on."""
    return math.log1p(max(0.0, value)) if uses_log(series_key) else value


def subject_id_for(series_key):
    """sa_profiles.subject_id is VARCHAR(64); a long Home Assistant entity id is shortened with a
    stable hash so two long keys can never collide on a truncated prefix."""
    if len(series_key) <= 64:
        return series_key
    import hashlib

    return series_key[:51] + "~" + hashlib.sha1(series_key.encode()).hexdigest()[:12]


# --- Small robust statistics ---------------------------------------------------------------


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


def weighted_mad_sigma(values, weights):
    """1.4826 x weighted MAD, the consistent estimator of a normal sigma. (centre, sigma) or
    (None, None)."""
    centre = weighted_median(values, weights)
    if centre is None:
        return None, None
    return centre, 1.4826 * weighted_median([abs(v - centre) for v in values], weights)


def theil_sen(xs, ys):
    """Robust slope: the median of all pairwise slopes. Evenly subsampled beyond
    COVARIATE_MAX_PAIRS points so the cost stays bounded."""
    n = len(xs)
    if n > COVARIATE_MAX_PAIRS:
        step = n / COVARIATE_MAX_PAIRS
        picks = [int(i * step) for i in range(COVARIATE_MAX_PAIRS)]
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


def two_sided_p(z):
    """P(|Z| >= |z|) for a standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# --- The model -----------------------------------------------------------------------------


def _hour_effects(points, ref_date):
    """e[h]: recency-weighted median, over days, of (value - that day's mean), centred on zero."""
    by_date = {}
    for p in points:
        by_date.setdefault(p["date"], []).append(p)
    devs = {h: ([], []) for h in range(24)}
    for day, day_points in by_date.items():
        if len(day_points) < MIN_DAY_POINTS:
            continue
        mean = sum(p["value"] for p in day_points) / len(day_points)
        weight = 0.5 ** (max(0, (ref_date - day).days) / HALF_LIFE_DAYS)
        for p in day_points:
            devs[p["hour"]][0].append(p["value"] - mean)
            devs[p["hour"]][1].append(weight)
    effects = []
    for hour in range(24):
        values, weights = devs[hour]
        effects.append(weighted_median(values, weights) if len(values) >= 3 else 0.0)
    centre = sum(effects) / 24.0
    return [e - centre for e in effects]


def level_at(effects, recent):
    """Local level from `recent` = [(lag_hours, hour_local, value)] (lag 1 = the previous hour):
    a lag-weighted mean of the hour-effect-adjusted values. None if too few points."""
    usable = [(lag, h, v) for lag, h, v in recent if 1 <= lag <= LEVEL_HOURS]
    if len(usable) < MIN_LEVEL_POINTS:
        return None
    total = weight_sum = 0.0
    for lag, hour, value in usable:
        w = 0.5 ** (lag / LEVEL_HALF_LIFE_HOURS)
        total += w * (value - effects[hour])
        weight_sum += w
    return total / weight_sum


def _recent_for(index, by_time, t):
    """The previous LEVEL_HOURS hours of a series as [(lag, hour_local, value)]."""
    recent = []
    for lag in range(1, LEVEL_HOURS + 1):
        p = by_time.get(t - timedelta(hours=lag))
        if p is not None:
            recent.append((lag, p["hour"], p["value"]))
    return recent


def _residuals(points, effects, ref_date, covariate=None):
    """One-step-ahead residuals r_t = y_t - (L_t + e[h]) for every hour with a level, with their
    recency weights and (when a covariate is given) the covariate anomaly at that hour."""
    by_time = {p["t"]: p for p in points}
    cov_by_time = {c["t"]: c["value"] for c in covariate} if covariate else None
    out = []
    for p in points:
        level = level_at(effects, _recent_for(None, by_time, p["t"]))
        if level is None:
            continue
        r = p["value"] - (level + effects[p["hour"]])
        anomaly = None
        if cov_by_time is not None and p["t"] in cov_by_time:
            prior = [
                cov_by_time[p["t"] - timedelta(hours=lag)]
                for lag in range(1, LEVEL_HOURS + 1)
                if (p["t"] - timedelta(hours=lag)) in cov_by_time
            ]
            if len(prior) >= MIN_LEVEL_POINTS:
                anomaly = cov_by_time[p["t"]] - sum(prior) / len(prior)
        weight = 0.5 ** (max(0, (ref_date - p["date"]).days) / HALF_LIFE_DAYS)
        out.append({"t": p["t"], "r": r, "w": weight, "c": anomaly})
    return out


def _select_covariate(residuals, name):
    """(beta, detail) if the covariate earns its place on a held-out final 30 %, else None."""
    pairs = [(x["c"], x["r"], x["t"]) for x in residuals if x["c"] is not None]
    detail = {"name": name, "overlap_hours": len(pairs), "used": False}
    if len(pairs) < MIN_COVARIATE_HOURS:
        detail["note"] = f"under {MIN_COVARIATE_HOURS} hours of overlap"
        return None, detail
    pairs.sort(key=lambda p: p[2])
    cut = int(len(pairs) * 0.7)
    train, test = pairs[:cut], pairs[cut:]
    beta = theil_sen([c for c, _, _ in train], [r for _, r, _ in train])

    def mad(values):
        centre = weighted_median(values, [1.0] * len(values))
        return weighted_median([abs(v - centre) for v in values], [1.0] * len(values))

    before = mad([r for _, r, _ in test])
    after = mad([r - beta * c for c, r, _ in test])
    improvement = 1.0 - after / before if before > 0 else 0.0
    detail.update({"beta": beta, "improvement": round(improvement, 4)})
    if improvement < COVARIATE_MIN_IMPROVEMENT:
        detail["note"] = "did not reduce held-out error enough"
        return None, detail
    detail["used"] = True
    # Refit the slope on all the data now that it has been validated.
    return theil_sen([c for c, _, _ in pairs], [r for _, r, _ in pairs]), detail


def fit_points(series_key, points, ref_date, covariate=None, covariate_name="outdoor_temp_c"):
    """Profile for one series, or None if it can't support one. `points`: dicts with t (hour start,
    naive UTC), date and hour (local), value, coverage; one per observed hour."""
    points = sorted(
        (
            p
            for p in points
            if p["coverage"] >= MIN_COVERAGE and p["value"] is not None and p["date"] <= ref_date
        ),
        key=lambda p: p["t"],
    )
    if len(points) < MIN_HOURS_TO_FIT:
        return None
    values = sorted(p["value"] for p in points)
    spread = values[int(len(values) * 0.9)] - values[int(len(values) * 0.1)]
    if values[-1] - values[0] <= 0:
        return None  # constant: nothing to learn (a tablet battery stuck at 90 %)
    diffs = [b["value"] - a["value"] for a, b in zip(points, points[1:])]
    if diffs and sum(1 for d in diffs if d >= 0) / len(diffs) > 0.98 and values[-1] > values[0]:
        return None  # a counter (uptime), not a quantity with a normal range

    effects = _hour_effects(points, ref_date)
    residuals = _residuals(points, effects, ref_date, covariate)
    if len(residuals) < MIN_STABILITY_RESIDUALS:
        return None

    beta, cov_detail = (None, None)
    if covariate:
        beta, cov_detail = _select_covariate(residuals, covariate_name)
    adjusted = [
        (x["r"] - (beta * x["c"] if beta is not None and x["c"] is not None else 0.0))
        for x in residuals
    ]
    weights = [x["w"] for x in residuals]
    bias, sigma = weighted_mad_sigma(adjusted, weights)
    sigma = max(sigma, SIGMA_FLOOR_FRACTION * spread, 1e-6)

    # Stability: has the forecast error grown lately? (recent week vs. the two weeks before it)
    recent_cut = ref_date - timedelta(days=STABILITY_RECENT_DAYS - 1)
    prior_cut = recent_cut - timedelta(days=STABILITY_PRIOR_DAYS)
    recent_r = [r for r, x in zip(adjusted, residuals) if x["t"].date() >= recent_cut]
    prior_r = [r for r, x in zip(adjusted, residuals) if prior_cut <= x["t"].date() < recent_cut]
    detail = {}
    if len(recent_r) >= MIN_STABILITY_RESIDUALS and len(prior_r) >= MIN_STABILITY_RESIDUALS:
        _, s_recent = weighted_mad_sigma(recent_r, [1.0] * len(recent_r))
        _, s_prior = weighted_mad_sigma(prior_r, [1.0] * len(prior_r))
        ratio = s_recent / s_prior if s_prior and s_prior > 0 else 1.0
        stability = 1.0 - _clamp(ratio - 1.0)
        detail = {"sigma_recent": round(s_recent, 4), "sigma_prior": round(s_prior, 4)}
    else:
        stability = STABILITY_UNKNOWN
        detail = {"note": "not enough history to measure"}

    last_t = points[-1]["t"]
    window_start = last_t - timedelta(hours=RECENT_HOURS - 1)
    recent_pts = [p for p in points if p["t"] >= window_start]
    coverage = _clamp(len(recent_pts) / RECENT_HOURS)
    quality = (
        _clamp(sum(p["coverage"] for p in recent_pts) / len(recent_pts), QUALITY_FLOOR, 1.0)
        if recent_pts
        else QUALITY_FLOOR
    )
    return Profile(
        learner=NAME,
        learner_version=VERSION,
        subject_type="series",
        subject_id=subject_id_for(series_key),
        signal=SIGNAL,
        params={
            "series_key": series_key,
            "effects": [round(e, 5) for e in effects],
            "sigma": round(sigma, 6),
            "bias": round(bias, 6),
            "level_hours": LEVEL_HOURS,
            "level_half_life_hours": LEVEL_HALF_LIFE_HOURS,
            "covariate": cov_detail,
            "beta": beta,
            "stability_detail": detail,
            "value_range": [values[0], values[-1]],
            "log": uses_log(series_key),
        },
        n_eff=round(sum(weights), 3),
        coverage=round(coverage, 4),
        source_quality=round(quality, 4),
        stability=round(stability, 4),
        fitted_from=points[0]["date"],
        fitted_to=ref_date,
    )


class ScalarLearner(Learner):
    name = NAME
    version = VERSION

    def expected(self, params, recent, hour_local, covariate_anomaly=None):
        """(mu, sigma) for the target hour, or None when there is too little recent data."""
        level = level_at(params["effects"], recent)
        if level is None:
            return None
        mu = level + params["effects"][hour_local] + params.get("bias", 0.0)
        beta = params.get("beta")
        if beta is not None and covariate_anomaly is not None:
            mu += beta * covariate_anomaly
        return mu, params["sigma"]

    def z_score(self, profile, state):
        """(z, mu, sigma) for an observed value, or None."""
        exp = self.expected(
            profile.params,
            state["recent"],
            state["local_dt"].hour,
            state.get("covariate_anomaly"),
        )
        if exp is None:
            return None
        mu, sigma = exp
        return (state["value"] - mu) / sigma, mu, sigma

    def score(self, profile, state, now):
        """A deviation Inference if |z| >= MIN_ABS_Z, else None. state: {"value", "recent":
        [(lag_hours, hour_local, value)], "local_dt", optional "covariate_anomaly"}."""
        scored = self.z_score(profile, state)
        if scored is None:
            return None
        z, mu, sigma = scored
        if abs(z) < MIN_ABS_Z:
            return None
        p = max(two_sided_p(z), 1e-12)
        terms = confidence.Confidence(
            confidence.sufficiency(profile.n_eff),
            profile.coverage,
            profile.source_quality,
            profile.stability,
        )
        hour = state["local_dt"].hour
        return Inference(
            kind="deviation",
            subject_type="series",
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=state.get("window_start")
            or now.replace(minute=0, second=0, microsecond=0),
            window_end=now.replace(microsecond=0),
            context={"series": profile.params["series_key"], "hour_local": hour},
            observed={"value": round(state["value"], 4), "direction": "high" if z > 0 else "low"},
            expected={"mu": round(mu, 4), "sigma": round(sigma, 4), "z": round(z, 3)},
            probability=round(p, 12),
            surprise=round(-math.log2(p), 3),
            confidence=round(terms.value, 4),
            n_eff=profile.n_eff,
            evidence={"terms": terms.as_dict(), "series": profile.params["series_key"]},
            expires_at=now + timedelta(hours=6),
        )

    def fit(self, lake_dir, ref=None, series=None):
        """Profiles for every eligible series in the gold layer."""
        grouped, flags, ref_default = load_series(lake_dir)
        ref = ref or ref_default
        covariate = grouped.get(COVARIATE_SERIES)
        profiles = []
        for key, points in sorted(grouped.items()):
            if series and key not in series:
                continue
            if flags.get(key):
                continue  # describes Home Assistant's old home, not the household
            profile = fit_points(
                key, points, ref, covariate=None if key == COVARIATE_SERIES else covariate
            )
            if profile is not None:
                profiles.append(profile)
        logger.info(f"scalar: fitted {len(profiles)} series as of {ref}")
        return profiles


# The household's outdoor temperature series (its own get_weather() record), used as the covariate.
COVARIATE_SERIES = "weather:temperature_c"


# --- Reading the lake ----------------------------------------------------------------------


def load_series(lake_dir):
    """({series_key: [point dicts]}, {series_key: describes_ha_home}, latest local date). Includes
    the household's outdoor temperature (silver weather_hourly) as the covariate series."""
    import os

    gold = os.path.join(lake_dir, "gold", "scalar_hourly", "part-0.parquet")
    if not os.path.exists(gold):
        return {}, {}, None
    con = duckdb.connect()
    try:
        grouped = {}
        for key, t, d, h, mean, cov in con.execute(
            f"SELECT series_key, bucket_utc, date_local, hour_local, mean, coverage "
            f"FROM read_parquet('{gold}') WHERE mean IS NOT NULL ORDER BY series_key, bucket_utc"
        ).fetchall():
            grouped.setdefault(key, []).append(
                {
                    "t": t,
                    "date": d,
                    "hour": h,
                    "value": to_model(key, float(mean)),
                    "coverage": float(cov),
                }
            )
        flags = {}
        entities = os.path.join(lake_dir, "silver", "ha_entities", "part-0.parquet")
        if os.path.exists(entities):
            for entity_id, describes in con.execute(
                f"SELECT entity_id, describes_ha_home FROM read_parquet('{entities}')"
            ).fetchall():
                flags["ha:" + entity_id] = bool(describes)
        weather = os.path.join(lake_dir, "silver", "weather_hourly", "part-0.parquet")
        if os.path.exists(weather):
            rows = con.execute(
                f"SELECT bucket_utc, CAST(bucket_local AS DATE), hour(bucket_local), temperature_c "
                f"FROM read_parquet('{weather}') WHERE temperature_c IS NOT NULL "
                f"ORDER BY bucket_utc"
            ).fetchall()
            if rows:
                grouped[COVARIATE_SERIES] = [
                    {"t": t, "date": d, "hour": h, "value": float(v), "coverage": 1.0}
                    for t, d, h, v in rows
                ]
        latest = max((p["date"] for pts in grouped.values() for p in pts), default=None)
        return grouped, flags, latest
    finally:
        con.close()


def run_fit(lake_dir, conn, now_utc=None):
    """The nightly job: fit every eligible series and store the profiles."""
    learner = ScalarLearner()
    profiles = learner.fit(lake_dir)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    found = detect_recent(lake_dir, now_utc=now_utc)
    for inference in found:
        inference_store.upsert_inference(conn, inference)
    return {"profiles": len(profiles), "removed": removed, "deviations": len(found)}


# --- Replay and backtest (walk-forward, no leakage) ----------------------------------------


def backtest(lake_dir, series_key, start, end, learner=None):
    """z for every observed hour in [start, end] (local dates); each day uses a profile fitted
    only on days before it. Returns [{"t", "value", "z", "mu", "sigma"}]."""
    learner = learner or ScalarLearner()
    grouped, _flags, _ref = load_series(lake_dir)
    points = grouped.get(series_key, [])
    covariate = grouped.get(COVARIATE_SERIES) if series_key != COVARIATE_SERIES else None
    by_time = {p["t"]: p for p in points}
    out = []
    day = start
    while day <= end:
        ref = day - timedelta(days=1)
        profile = fit_points(series_key, [p for p in points if p["date"] <= ref], ref, covariate)
        if profile is not None:
            for p in points:
                if p["date"] != day or p["coverage"] < MIN_COVERAGE:
                    continue
                state = {
                    "value": p["value"],
                    "recent": _recent_for(None, by_time, p["t"]),
                    "local_dt": datetime.combine(p["date"], datetime.min.time()).replace(
                        hour=p["hour"]
                    ),
                }
                scored = learner.z_score(profile, state)
                if scored is not None:
                    z, mu, sigma = scored
                    out.append({"t": p["t"], "value": p["value"], "z": z, "mu": mu, "sigma": sigma})
        day += timedelta(days=1)
    return out


def detect_recent(lake_dir, hours=48, learner=None, now_utc=None):
    """Batch deviations for the last `hours` of every fitted series, as Inferences: the nightly
    L1 output for series that have no live path (battery, speed tests, Wi-Fi)."""
    learner = learner or ScalarLearner()
    now_utc = now_utc or utcnow()
    grouped, flags, ref = load_series(lake_dir)
    covariate = grouped.get(COVARIATE_SERIES)
    found = []
    for key, points in sorted(grouped.items()):
        if key == COVARIATE_SERIES or flags.get(key) or not points:
            continue
        profile = fit_points(key, points, ref, covariate)
        if profile is None:
            continue
        by_time = {p["t"]: p for p in points}
        horizon = points[-1]["t"]
        for p in points:
            if p["t"] < horizon - timedelta(hours=hours) or p["coverage"] < MIN_COVERAGE:
                continue
            state = {
                "value": p["value"],
                "recent": _recent_for(None, by_time, p["t"]),
                "local_dt": datetime.combine(p["date"], datetime.min.time()).replace(
                    hour=p["hour"]
                ),
                "window_start": p["t"],
            }
            inference = learner.score(profile, state, p["t"] + timedelta(hours=1))
            if inference is not None:
                inference.computed_at = now_utc
                found.append(inference)
    return found


if __name__ == "__main__":
    import os

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    lake = os.environ.get("SA_LAKE_DIR", "/lake")
    for profile in ScalarLearner().fit(lake):
        print(
            f"{profile.params['series_key']:66s} sigma={profile.params['sigma']:<9} "
            f"n_eff={profile.n_eff:<8} cov={profile.coverage} q={profile.source_quality} "
            f"stab={profile.stability}"
        )
