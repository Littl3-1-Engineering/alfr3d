"""Household day learner: is today running differently than usual for this household? (SA-10.)
The first LAYER-2 inference: it combines layer-1 evidence about two day features and their
confidence into one statement, written with layer = 2 and the parent evidence attached.

Features, both measured up to CUTOFF_HOUR local so a day in progress is comparable with the
completed days it is judged against:
- `devices`: distinct devices active since midnight (the house is "awake"),
- `first_minute`: minutes after midnight of the first device to come online (CUTOFF_HOUR * 60
  if none did).

Each feature has a layer-1 model per day type (weekday vs weekend / Ontario holiday): a recency-
weighted median and MAD sigma (robust: a day the router rebooted must not widen the band), falling
back to all days when a day type has too little history. A feature's deviation is a two-sided normal
tail p_i with a confidence c_i (shared definition). Layer 2 then combines them with Fisher's
method, evidence weighted by confidence:

    X = -2 * sum(c_i * ln p_i)        p = P(chi-square with 2k dof >= X)

so a low-confidence feature counts for less, and several mild deviations that agree add up where
neither would alone. Like the legacy rule, it still takes more than one metric: each feature must be
at least mildly off (p <= MIN_EACH_P), so a single noisy number can't make a day unusual.
Weighting by c_i makes X only approximately chi-square; P_FLAG was therefore
chosen from the walk-forward backtest's actual firing rate, not read off a table.

The legacy rule fired only if BOTH features were out of range after the household's typical last
activity hour, using a median-free min/max range and fixed tolerance.
"""

import logging
import math
import os
import sys
from datetime import date, datetime, timedelta

import duckdb

from sa import confidence, inference_store
from sa.learners import presence
from sa.learners.base import Inference, Learner, Profile, utcnow
from sa.learners.scalar import weighted_mad_sigma

logger = logging.getLogger("SAHouseholdDay")

NAME = "household_day"
VERSION = "1"
SIGNAL = "household.day"

CUTOFF_HOUR = 18
HALF_LIFE_DAYS = 28.0
MIN_DAYS = 21
MIN_CELL_WEIGHT = 5.0
SIGMA_FLOOR = {"devices": 1.0, "first_minute": 30.0}
FEATURES = ("devices", "first_minute")
MIN_EACH_P = 0.25  # every feature must be at least mildly off: one noisy metric is just a day
P_FLAG = 0.01  # chosen from the backtest (see todo_lf4b_baseline_ports.md)
STABILITY_UNKNOWN = 0.5
QUALITY = 1.0


def fisher_p(ps, weights):
    """P(chi-square_{2k} >= X) for X = -2 * sum(w * ln p). Closed form for even degrees of
    freedom: exp(-X/2) * sum_{j<k} (X/2)^j / j!."""
    k = len(ps)
    x = -2.0 * sum(w * math.log(max(p, 1e-300)) for p, w in zip(ps, weights))
    half = x / 2.0
    term, total = 1.0, 1.0
    for j in range(1, k):
        term *= half / j
        total += term
    return min(1.0, math.exp(-half) * total)


def two_sided_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


class HouseholdDayLearner(Learner):
    name = NAME
    version = VERSION

    def fit_days(self, days, ref, coverage=1.0):
        """Profile from [{"date","devices","first_minute"}] completed days up to `ref`, or None."""
        days = [d for d in days if d["date"] <= ref and d["devices"] is not None]
        if len(days) < MIN_DAYS:
            return None
        weights = {
            d["date"]: 0.5 ** (max(0, (ref - d["date"]).days) / HALF_LIFE_DAYS) for d in days
        }
        params = {"cutoff_hour": CUTOFF_HOUR, "features": {}}
        stabilities = []
        for feature in FEATURES:
            pooled = [(d[feature], weights[d["date"]]) for d in days if d[feature] is not None]
            cells = {}
            for kind in ("weekday", "offday"):
                vals = [
                    (d[feature], weights[d["date"]])
                    for d in days
                    if d[feature] is not None and presence._daytype(d["date"]) == kind
                ]
                use = vals if sum(w for _, w in vals) >= MIN_CELL_WEIGHT else pooled
                v, w = [x for x, _ in use], [y for _, y in use]
                centre, sigma = weighted_mad_sigma(v, w)
                cells[kind] = {
                    "median": round(centre, 3),
                    "sigma": round(max(sigma, SIGMA_FLOOR[feature]), 3),
                    "weight": round(sum(w), 3),
                    "pooled": use is pooled,
                }
            params["features"][feature] = cells
            recent = [
                d[feature]
                for d in days
                if d["date"] > ref - timedelta(days=14) and d[feature] is not None
            ]
            prior = [
                d[feature]
                for d in days
                if ref - timedelta(days=42) < d["date"] <= ref - timedelta(days=14)
                and d[feature] is not None
            ]
            if len(recent) >= 7 and len(prior) >= 14:
                _, sigma_all = weighted_mad_sigma(prior, [1.0] * len(prior))
                shift = abs(_median(recent) - _median(prior)) / max(sigma_all, SIGMA_FLOOR[feature])
                stabilities.append(1.0 / (1.0 + shift))
        stability = sum(stabilities) / len(stabilities) if stabilities else STABILITY_UNKNOWN
        return Profile(
            learner=self.name,
            learner_version=self.version,
            subject_type="household",
            subject_id="household",
            signal=SIGNAL,
            params=params,
            n_eff=round(sum(weights.values()), 3),
            coverage=round(coverage, 4),
            source_quality=QUALITY,
            stability=round(stability, 4),
            fitted_from=min(d["date"] for d in days),
            fitted_to=ref,
        )

    def fit(self, lake_dir, ref=None):
        data = load_days(lake_dir)
        if not data["days"]:
            return []
        ref = ref or data["days"][-1]["date"]
        profile = self.fit_days(data["days"], ref, data["coverage"])
        return [profile] if profile else []

    def score(self, profile, state, now):
        """A layer-2 deviation if the combined p <= P_FLAG, else None. state: {"devices",
        "first_minute", "local_dt"}; `first_minute` may be None (nothing active yet)."""
        day = state["local_dt"].date()
        kind = presence._daytype(day)
        parents, ps, cs = [], [], []
        for feature in FEATURES:
            value = state.get(feature)
            if value is None:
                continue
            cell = profile.params["features"][feature][kind]
            z = (value - cell["median"]) / cell["sigma"]
            p = max(two_sided_p(z), 1e-12)
            c = confidence.Confidence(
                confidence.sufficiency(cell["weight"]),
                profile.coverage,
                profile.source_quality,
                profile.stability,
            )
            parents.append(
                {
                    "feature": feature,
                    "value": round(value, 2),
                    "expected": cell["median"],
                    "z": round(z, 3),
                    "p": round(p, 8),
                    "confidence": round(c.value, 4),
                }
            )
            ps.append(p)
            cs.append(c.value)
        if len(ps) < 2:
            return None
        if max(ps) > MIN_EACH_P:
            return None
        p_comb = fisher_p(ps, cs)
        if p_comb > P_FLAG:
            return None
        p_comb = max(p_comb, 1e-12)
        conf = sum(cs) / len(cs)
        midnight = datetime.combine(day, datetime.min.time())
        local = state["local_dt"]
        return Inference(
            layer=2,
            kind="deviation",
            subject_type="household",
            subject_id="household",
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=now - (local - midnight),
            window_end=now.replace(microsecond=0),
            context={"daytype": kind, "cutoff_hour": CUTOFF_HOUR},
            observed={f["feature"]: f["value"] for f in parents},
            expected={f["feature"]: f["expected"] for f in parents},
            probability=round(p_comb, 12),
            surprise=round(-math.log2(p_comb), 3),
            confidence=round(conf, 4),
            n_eff=profile.n_eff,
            evidence={"method": "fisher_confidence_weighted", "parents": parents},
            expires_at=now + timedelta(hours=12),
        )


def _median(values):
    v = sorted(values)
    return v[len(v) // 2]


_DAYS_SQL = """
WITH days AS (
  SELECT UNNEST(generate_series(CAST(MIN(start_local) AS DATE), CAST(MAX(start_local) AS DATE),
                                INTERVAL 1 DAY))::DATE AS d FROM sess),
ok AS (  -- days on which the collector observed every hour of the window
  SELECT date_local AS d FROM grid WHERE hour_local < {cutoff} AND observed
  GROUP BY 1 HAVING COUNT(DISTINCT hour_local) = {cutoff}),
act AS (
  SELECT d.d, s.device_id
  FROM days d JOIN sess s
    ON s.start_local < CAST(d.d AS TIMESTAMP) + INTERVAL {cutoff} HOUR
   AND s.end_local > CAST(d.d AS TIMESTAMP)),
firsts AS (  -- the first device to COME ONLINE that day (always-on gear spans midnight)
  SELECT d.d, MIN(epoch(s.start_local - CAST(d.d AS TIMESTAMP)) / 60.0) AS first_minute
  FROM days d JOIN sess s
    ON s.start_local >= CAST(d.d AS TIMESTAMP)
   AND s.start_local < CAST(d.d AS TIMESTAMP) + INTERVAL {cutoff} HOUR
  GROUP BY d.d)
SELECT days.d, COUNT(DISTINCT act.device_id), COALESCE(firsts.first_minute, {cutoff} * 60.0)
FROM days JOIN ok ON ok.d = days.d
LEFT JOIN act ON act.d = days.d LEFT JOIN firsts ON firsts.d = days.d
GROUP BY days.d, firsts.first_minute ORDER BY days.d
"""


def load_days(lake_dir):
    """{"days": [{"date","devices","first_minute"}], "coverage"}: completed, fully observed local
    days (up to CUTOFF_HOUR), from silver device_sessions and the presence grid's observed flag."""
    sessions_file = os.path.join(lake_dir, "silver", "device_sessions", "part-0.parquet")
    grid_file = os.path.join(lake_dir, "gold", "presence_grid", "part-0.parquet")
    if not (os.path.exists(sessions_file) and os.path.exists(grid_file)):
        return {"days": [], "coverage": 0.0}
    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW sess AS SELECT * FROM read_parquet('{sessions_file}')")
        con.execute(
            "CREATE VIEW grid AS SELECT date_local, hour_local, bool_or(observed) AS observed "
            f"FROM read_parquet('{grid_file}') GROUP BY 1, 2"
        )
        rows = con.execute(_DAYS_SQL.format(cutoff=CUTOFF_HOUR)).fetchall()
        days = [{"date": d, "devices": n, "first_minute": fm if n else None} for d, n, fm in rows]
        total = con.execute(
            f"SELECT COUNT(DISTINCT date_local) FROM grid WHERE hour_local < {CUTOFF_HOUR}"
        ).fetchone()[0]
        coverage = len(days) / total if total else 0.0
        return {"days": days, "coverage": min(1.0, coverage)}
    finally:
        con.close()


def run_fit(lake_dir, conn, now_utc=None):
    profiles = HouseholdDayLearner().fit(lake_dir)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    return {"profiles": len(profiles), "removed": removed}


def backtest(lake_dir, start, end, learner=None):
    """Walk-forward: [{"date","devices","first_minute","p","flagged"}] for each day in [start,
    end], each scored on a profile fitted on the days before it."""
    learner = learner or HouseholdDayLearner()
    data = load_days(lake_dir)
    out = []
    for day in data["days"]:
        if not (start <= day["date"] <= end):
            continue
        profile = learner.fit_days(data["days"], day["date"] - timedelta(days=1), data["coverage"])
        if profile is None or day["first_minute"] is None:
            continue
        state = {
            "devices": day["devices"],
            "first_minute": day["first_minute"],
            "local_dt": datetime.combine(day["date"], datetime.min.time())
            + timedelta(hours=CUTOFF_HOUR),
        }
        # p without the threshold: score() returns None when unremarkable, so recompute directly.
        kind = presence._daytype(day["date"])
        ps, cs = [], []
        for feature in FEATURES:
            cell = profile.params["features"][feature][kind]
            z = (state[feature] - cell["median"]) / cell["sigma"]
            ps.append(max(two_sided_p(z), 1e-12))
            cs.append(
                confidence.Confidence(
                    confidence.sufficiency(cell["weight"]),
                    profile.coverage,
                    profile.source_quality,
                    profile.stability,
                ).value
            )
        p = fisher_p(ps, cs)
        out.append({**day, "p": p, "flagged": p <= P_FLAG})
    return out


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    for profile in HouseholdDayLearner().fit(os.environ.get("SA_LAKE_DIR", "/lake")):
        print(profile.params)
