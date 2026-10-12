"""Household day learner: is today running differently than usual for this household? (SA-10.)
The first LAYER-2 inference: it combines layer-1 evidence about two day features and their
confidence into one statement, written with layer = 2 and the parent evidence attached.

Features, both measured up to CUTOFF_HOUR local so a day in progress is comparable with the
completed days it is judged against:
- `devices`: distinct devices active since midnight (the house is "awake"),
- `first_minute`: minutes after midnight of the first device to come online (CUTOFF_HOUR * 60
  if none did),
- `home_minutes`: person-minutes at home (phones of owners and residents, from the same island
  rule as silver presence_intervals). Added in v2: the first two features describe *devices*, and
  most of them are always-on gear, so a day the household was out looks normal to them. A day
  Athos is out when he is normally home 9-17 is a drop of several hundred person-minutes here.

Each feature has a layer-1 model per day type (weekday vs weekend / Ontario holiday): a recency-
weighted median and MAD sigma (robust: a day the router rebooted must not widen the band), falling
back to all days when a day type has too little history. A feature's deviation is a two-sided normal
tail p_i with a confidence c_i (shared definition). Layer 2 then combines them with Fisher's
method, evidence weighted by confidence:

    X = -2 * sum(c_i * ln p_i)        p = P(chi-square with 2k dof >= X)

so a low-confidence feature counts for less, and several mild deviations that agree add up where
neither would alone. Like the legacy rule, it still takes more than one metric: at least two
features must be mildly off (p <= MIN_EACH_P), so a single noisy number can't make a day unusual.
Fisher runs over every feature, the unremarkable ones included, so choosing which features to
combine after looking at them cannot flatter the p-value.
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
VERSION = "2"
SIGNAL = "household.day"

CUTOFF_HOUR = 18
HALF_LIFE_DAYS = 28.0
MIN_DAYS = 21
MIN_CELL_WEIGHT = 5.0
SIGMA_FLOOR = {"devices": 1.0, "first_minute": 30.0, "home_minutes": 60.0}
FEATURES = ("devices", "first_minute", "home_minutes")
HOME_USER_TYPES = ("owner", "technoking", "resident")  # whose phones count as "the household"
PRESENCE_GAP_MINUTES = 45  # silver's rule: sightings further apart than this are separate stays
MIN_EACH_P = 0.25  # a feature this unlikely counts as "off"
MIN_FEATURES_OFF = 2  # one noisy metric is just a day
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
            pooled = [(d[feature], weights[d["date"]]) for d in days if d.get(feature) is not None]
            if len(pooled) < MIN_DAYS:
                continue  # e.g. home_minutes before presence existed: leave the feature out
            cells = {}
            for kind in ("weekday", "offday"):
                vals = [
                    (d[feature], weights[d["date"]])
                    for d in days
                    if d.get(feature) is not None and presence._daytype(d["date"]) == kind
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
                if d["date"] > ref - timedelta(days=14) and d.get(feature) is not None
            ]
            prior = [
                d[feature]
                for d in days
                if ref - timedelta(days=42) < d["date"] <= ref - timedelta(days=14)
                and d.get(feature) is not None
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
            if value is None or feature not in profile.params["features"]:
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
        if len(ps) < MIN_FEATURES_OFF:
            return None
        if sum(1 for p in ps if p <= MIN_EACH_P) < MIN_FEATURES_OFF:
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


def home_minutes(sightings, window_start, window_end, gap_minutes=PRESENCE_GAP_MINUTES):
    """Person-minutes at home inside [window_start, window_end): {user_id: [sighting datetimes]}
    -> minutes. Sightings of one person closer than `gap_minutes` form one stay, and a stay
    covers first..last sighting -- silver presence_intervals' rule, so a live day and the fitted
    days are measured the same way. Stays may begin before the window (clipped to it)."""
    gap = timedelta(minutes=gap_minutes)
    total = 0.0
    for times in sightings.values():
        times = sorted(set(times))
        start = prev = None
        for t in times:
            if start is None:
                start = prev = t
            elif t - prev <= gap:
                prev = t
            else:
                total += _overlap_minutes(start, prev, window_start, window_end)
                start = prev = t
        if start is not None:
            total += _overlap_minutes(start, prev, window_start, window_end)
    return total


def _overlap_minutes(start, end, window_start, window_end):
    lo, hi = max(start, window_start), min(end, window_end)
    return max(0.0, (hi - lo).total_seconds() / 60.0)


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
  GROUP BY d.d){home_cte}
SELECT days.d, COUNT(DISTINCT act.device_id), COALESCE(firsts.first_minute, {cutoff} * 60.0),
       {home_select}
FROM days JOIN ok ON ok.d = days.d
LEFT JOIN act ON act.d = days.d LEFT JOIN firsts ON firsts.d = days.d
{home_join}
GROUP BY days.d, firsts.first_minute{home_group} ORDER BY days.d
"""

# Person-minutes at home before the cutoff, for the people who live here (gold presence_grid joined
# to the user type silver recorded). Absent when presence was never built.
_HOME_SQL = """,
homes AS (
  SELECT g.date_local AS d, SUM(g.minutes_home) AS m
  FROM grid_users g JOIN user_types u ON u.user_id = g.user_id
  WHERE g.hour_local < {cutoff} GROUP BY 1)"""


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
        intervals_file = os.path.join(lake_dir, "silver", "presence_intervals", "part-0.parquet")
        has_home = os.path.exists(intervals_file)
        sql = _DAYS_SQL.format(
            cutoff=CUTOFF_HOUR,
            home_cte=_HOME_SQL.format(cutoff=CUTOFF_HOUR) if has_home else "",
            home_select="COALESCE(homes.m, 0.0)" if has_home else "NULL",
            home_join="LEFT JOIN homes ON homes.d = days.d" if has_home else "",
            home_group=", homes.m" if has_home else "",
        )
        if has_home:
            types = ", ".join("'" + t + "'" for t in HOME_USER_TYPES)
            con.execute(f"CREATE VIEW grid_users AS SELECT * FROM read_parquet('{grid_file}')")
            con.execute(
                "CREATE VIEW user_types AS SELECT DISTINCT user_id FROM "
                f"read_parquet('{intervals_file}') WHERE user_type IN ({types})"
            )
        rows = con.execute(sql).fetchall()
        days = [
            {"date": d, "devices": n, "first_minute": fm if n else None, "home_minutes": hm}
            for d, n, fm, hm in rows
        ]
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
        # p without the threshold: score() returns None when unremarkable, so recompute directly.
        kind = presence._daytype(day["date"])
        ps, cs = [], []
        for feature in FEATURES:
            if feature not in profile.params["features"] or day.get(feature) is None:
                continue
            cell = profile.params["features"][feature][kind]
            z = (day[feature] - cell["median"]) / cell["sigma"]
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
        off = sum(1 for q in ps if q <= MIN_EACH_P)
        out.append({**day, "p": p, "flagged": p <= P_FLAG and off >= MIN_FEATURES_OFF})
    return out


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    for profile in HouseholdDayLearner().fit(os.environ.get("SA_LAKE_DIR", "/lake")):
        print(profile.params)
