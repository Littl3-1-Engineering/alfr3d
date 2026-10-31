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
weighted median and MAD sigma, and the weighted past values themselves, from which its deviation is
scored as an empirical two-sided tail p_i (robust: a day the router rebooted must not widen the
band). Falls back to all days when a day type has too little history.

v4: the household chooses its own yardsticks and its own bar. Nothing here is hand-set per rule.

- Features are learned. Besides the three above, every event stream in the lake (a household_events
  type/subject/verb: music plays, notifications, routines, device commands) contributes its count
  up to the cutoff. A feature is kept only if it has enough days and varies (at least
  MIN_DISTINCT_VALUES distinct values), so streams that are constant or too new drop out on their
  own at each nightly fit.
- The day's statistic is Fisher's method over its TOP_K most surprising features (fewer if fewer
  exist), whichever they are: -2 * sum(ln p). Picking the most surprising looks flattering, so the
  bar is not read off a chi-square table; it is calibrated on the same statistic.
- The bar is learned. Each fit scores every past day against all the OTHER days (leave one out),
  which is exactly how a new day would be scored, and sets the bar at the surprise only
  TARGET_FLAG_RATE of those days reach. So the household sees about one unusual-day card in
  1 / TARGET_FLAG_RATE days whatever its own variability and however many features it has, and the
  bar moves as the household does. With fewer than MIN_CALIBRATION_DAYS days there is no bar and
  the rule stays quiet.
"""

import logging
import math
import os
import sys
from datetime import datetime, timedelta

import duckdb

from sa import confidence, inference_store, layer2
from sa.layer2 import fisher_p  # noqa: F401  (re-exported: tests and backtests import it here)
from sa.learners import presence
from sa.learners.base import Inference, Learner, Profile
from sa.learners.scalar import weighted_mad_sigma

logger = logging.getLogger("SAHouseholdDay")

NAME = "household_day"
VERSION = "4"
SIGNAL = "household.day"
SIGNAL_FEATURE = "household.day_feature"

CUTOFF_HOUR = 18
HALF_LIFE_DAYS = 28.0
MIN_DAYS = 21
MIN_CELL_WEIGHT = 5.0
SIGMA_FLOOR = {"device_share": 0.05, "first_minute": 30.0, "home_minutes": 60.0}
# device_share is the devices active today over the devices seen in the 14 days before: a device
# the household stops owning (deleted from the system) leaves the denominator after two weeks
# instead of reading as a permanently quiet house. first_minute is bimodal (a nightly reconnect at
# ~03:51 on most days, an earlier phone nap on the rest), so no feature is scored with a Gaussian z:
# each is its own empirical two-sided tail (see empirical_p).
FEATURES = ("device_share", "first_minute", "home_minutes")
EVENT_PREFIX = "event:"  # learned features: one per event stream, the day's count up to the cutoff
MIN_DISTINCT_VALUES = 3  # a feature that barely varies says nothing about an unusual day
INVENTORY_DAYS = 14
MIN_INVENTORY = 5
SAMPLE_DAYS = 180
HOME_USER_TYPES = ("owner", "technoking", "resident")  # whose phones count as "the household"
PRESENCE_GAP_MINUTES = 45  # silver's rule: sightings further apart than this are separate stays
TARGET_FLAG_RATE = 1.0 / 14.0  # the share of days the bar is calibrated to flag
TOP_K = 5  # features combined into the day's statistic
MIN_STATISTIC_FEATURES = 2  # a statistic needs at least this many features measured
MIN_CALIBRATION_DAYS = 28  # below this the bar is unknown and nothing is flagged
EXPLAIN_P = 0.15  # the card lists the combined features at least this unlikely
STABILITY_UNKNOWN = 0.5
QUALITY = 1.0
FAMILY_PREFIX = "household_day:"


def two_sided_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


def empirical_p(samples, value):
    """Two-sided tail probability of `value` among weighted past `samples` [(value, weight)],
    smoothed so a short history cannot claim certainty: twice the smaller of the weighted shares
    at or below and at or above it, each (S + 0.5) / (W + 1)."""
    total = sum(w for _, w in samples)
    lower = (sum(w for v, w in samples if v <= value) + 0.5) / (total + 1.0)
    upper = (sum(w for v, w in samples if v >= value) + 0.5) / (total + 1.0)
    return min(1.0, 2.0 * min(lower, upper))


def feature_names(days):
    """The fixed features, then every event stream any day carries, in a stable order."""
    events = sorted({k for d in days for k in d if k.startswith(EVENT_PREFIX)})
    return [*FEATURES, *events]


def _spread(feature, values, weights):
    """(centre, sigma) of a feature: weighted median and MAD sigma, falling back to the weighted
    standard deviation when most days share one value (a count that is usually the same)."""
    centre, sigma = weighted_mad_sigma(values, weights)
    if sigma <= 0.0:
        total = sum(weights)
        mean = sum(v * w for v, w in zip(values, weights)) / total
        sigma = math.sqrt(sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total)
    return centre, max(sigma, SIGMA_FLOOR.get(feature, 1e-3))


def top_bits(ps, k=TOP_K):
    """The day's statistic: surprise in bits of Fisher's method over its k most surprising
    features (all of them if fewer). None with too few features measured."""
    if len(ps) < MIN_STATISTIC_FEATURES:
        return None
    top = sorted(ps)[:k]
    return -math.log2(max(fisher_p(top, [1.0] * len(top)), 1e-12))


def loo_bits(days, features, weights):
    """The statistic (top_bits) of every day scored against all the OTHER days, the way a new day
    would be scored."""
    series = {}
    for feature in features:
        series[feature] = [
            (d["date"], presence._daytype(d["date"]), d[feature], weights[d["date"]])
            for d in days
            if d.get(feature) is not None
        ]
    bits = []
    for d in days:
        kind = presence._daytype(d["date"])
        ps = []
        for feature in features:
            value = d.get(feature)
            if value is None:
                continue
            others = [(v, w, k) for dt, k, v, w in series[feature] if dt != d["date"]]
            same = [(v, w) for v, w, k in others if k == kind]
            enough = sum(w for _, w in same) >= MIN_CELL_WEIGHT
            pool = same if enough else [(v, w) for v, w, _ in others]
            ps.append(max(empirical_p(pool, value), 1e-12))
        b = top_bits(ps)
        if b is not None:
            bits.append(b)
    return bits


def calibrate(days, features, weights, rate=TARGET_FLAG_RATE):
    """(bar_bits, number of days scored): the surprise only `rate` of the household's own days
    reach (see loo_bits). None for the bar when fewer than MIN_CALIBRATION_DAYS days could be
    scored."""
    bits = loo_bits(days, features, weights)
    if len(bits) < MIN_CALIBRATION_DAYS:
        return None, len(bits)
    bits.sort()
    index = min(len(bits) - 1, max(0, math.ceil(len(bits) * (1.0 - rate)) - 1))
    return round(bits[index], 3), len(bits)


class HouseholdDayLearner(Learner):
    name = NAME
    version = VERSION

    def fit_days(self, days, ref, coverage=1.0, calibrated=True):
        """Profile from [{"date","devices","first_minute", ...}] completed days up to `ref`, or
        None. Keeps the features that have MIN_DAYS days and vary, scores every day against the
        others to learn the bar, and records both. `calibrated=False` skips the (slower) bar."""
        days = [
            d
            for d in days
            if d["date"] <= ref
            and d["devices"] is not None
            and (ref - d["date"]).days <= SAMPLE_DAYS
        ]
        if len(days) < MIN_DAYS:
            return None
        weights = {
            d["date"]: 0.5 ** (max(0, (ref - d["date"]).days) / HALF_LIFE_DAYS) for d in days
        }
        params = {"cutoff_hour": CUTOFF_HOUR, "features": {}}
        stabilities = []
        for feature in feature_names(days):
            pooled = [(d[feature], weights[d["date"]]) for d in days if d.get(feature) is not None]
            if len(pooled) < MIN_DAYS or len({v for v, _ in pooled}) < MIN_DISTINCT_VALUES:
                continue  # too little history (e.g. a new stream), or it hardly varies
            cells = {}
            for kind in ("weekday", "offday"):
                vals = [
                    (d[feature], weights[d["date"]])
                    for d in days
                    if d.get(feature) is not None and presence._daytype(d["date"]) == kind
                ]
                use = vals if sum(w for _, w in vals) >= MIN_CELL_WEIGHT else pooled
                v, w = [x for x, _ in use], [y for _, y in use]
                centre, sigma = _spread(feature, v, w)
                cells[kind] = {
                    "median": round(centre, 3),
                    "sigma": round(sigma, 3),
                    "weight": round(sum(w), 3),
                    "pooled": use is pooled,
                    "samples": [[round(x, 4), round(y, 4)] for x, y in use],
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
                _, sigma_all = _spread(feature, prior, [1.0] * len(prior))
                shift = abs(_median(recent) - _median(prior)) / sigma_all
                stabilities.append(1.0 / (1.0 + shift))
        if len(params["features"]) < MIN_STATISTIC_FEATURES:
            return None
        if calibrated:
            bar, scored = calibrate(days, list(params["features"]), weights)
            params["calibration"] = {
                "bar_bits": bar,
                "days": scored,
                "target_rate": round(TARGET_FLAG_RATE, 4),
                "top_k": TOP_K,
            }
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

    def score_features(self, profile, state, now):
        """Layer-1 rows, one per feature the day has a value for: how improbable that value is for
        this household on this day type, with its confidence. Unremarkable features are included
        (state rows, any p): the layer-2 rule combines all of them, so picking which to combine
        after looking cannot flatter the p-value. state: {"device_share", "first_minute",
        "home_minutes", "local_dt"}; a value may be None (nothing measured yet)."""
        day = state["local_dt"].date()
        kind = presence._daytype(day)
        midnight = datetime.combine(day, datetime.min.time())
        window_start = (now - (state["local_dt"] - midnight)).replace(microsecond=0)
        rows = []
        calibration = profile.params.get("calibration") or {}
        for feature in profile.params["features"]:
            value = state.get(feature)
            if value is None:
                continue
            cell = profile.params["features"][feature][kind]
            z = (value - cell["median"]) / cell["sigma"]
            p = max(empirical_p([(v, w) for v, w in cell["samples"]], value), 1e-12)
            c = confidence.Confidence(
                confidence.sufficiency(cell["weight"]),
                profile.coverage,
                profile.source_quality,
                profile.stability,
            )
            rows.append(
                Inference(
                    kind="state",
                    subject_type="household",  # sa_inferences.subject_type is VARCHAR(16)
                    subject_id=feature,
                    signal=SIGNAL_FEATURE,
                    learner=self.name,
                    learner_version=self.version,
                    window_start=window_start,
                    window_end=now.replace(microsecond=0),
                    context={
                        "daytype": kind,
                        "cutoff_hour": CUTOFF_HOUR,
                        # The learned bar travels with the rows: layer 2 sees only rows.
                        "bar_bits": calibration.get("bar_bits"),
                        "top_k": calibration.get("top_k", TOP_K),
                    },
                    observed={"value": round(value, 2), "z": round(z, 3)},
                    expected={"median": cell["median"], "sigma": cell["sigma"]},
                    # Unrounded: the layer-2 rule fuses these, and rounding a tiny p to 12 places
                    # changes the combined p by percent.
                    probability=p,
                    surprise=round(-math.log2(p), 3),
                    confidence=c.value,
                    n_eff=cell["weight"],
                    # Each feature is its own family: the legacy rule treated them as independent
                    # evidence and P_FLAG was calibrated on that.
                    evidence={"family": FAMILY_PREFIX + feature, "feature": feature},
                    expires_at=now + timedelta(hours=12),
                )
            )
        return rows

    def score(self, profile, state, now):
        """The layer-2 deviation if the day is unusual, else None: the features scored above,
        fused by RULE. Kept for backtests and callers holding a profile rather than rows."""
        groups = RULE.groups(self.score_features(profile, state, now), {})
        return layer2.fuse(RULE, groups[0], now) if groups else None


class HouseholdUnusualDayRule(layer2.Rule):
    """SA-10 as a layer-2 rule: the Fisher p of the day's TOP_K most surprising features, against a
    bar the learner calibrated on this household's own days (see calibrate). Unweighted: the inputs
    are empirical tail probabilities, which smoothing keeps above ~0.5 / (days + 1), and weighting
    their logs by a confidence near 0.25 would make a small combined p unreachable."""

    name = NAME
    version = VERSION
    signal = SIGNAL
    subject_type = "household"
    min_bits = math.inf  # no bar learned yet: stay quiet (bar_bits reads the learned one)
    cap_at_best = False
    weight_by_confidence = False
    ttl_hours = 12

    def groups(self, parents, ctx):
        features = sorted(
            (p for p in parents if p.signal == SIGNAL_FEATURE and p.probability is not None),
            key=lambda p: p.probability,
        )
        if len(features) < MIN_STATISTIC_FEATURES:
            return []
        k = (features[0].context or {}).get("top_k") or TOP_K
        top = features[:k]
        return [layer2.Group("household", top[0], top)]

    def bar_bits(self, group):
        bar = (group.anchor.context or {}).get("bar_bits")
        return math.inf if bar is None else bar

    def observed(self, group):
        return {p.evidence["feature"]: p.observed["value"] for p in group.parents}

    def expected(self, group):
        return {p.evidence["feature"]: p.expected["median"] for p in group.parents}


RULE = HouseholdUnusualDayRule()


def _clock(minute):
    return f"{int(minute) // 60:02d}:{int(minute) % 60:02d}"


def _label(feature):
    """'event:audio/track/play_start' -> 'audio track play_start'."""
    parts = [p for p in feature[len(EVENT_PREFIX):].split("/") if p and p != "-"]
    return " ".join(parts)


def explain(inference):
    """The card's 'because' lines for a household_unusual_day inference: one per combined feature
    that was off (p <= EXPLAIN_P), plain units, value against the household's usual."""
    observed, expected = inference.observed or {}, inference.expected or {}
    off = {
        ref["feature"]
        for ref in (inference.evidence or {}).get("parents", [])
        if ref.get("feature") and ref["p"] is not None and ref["p"] <= EXPLAIN_P
    }
    lines = []
    if "device_share" in off:
        lines.append(
            f"{round(observed['device_share'] * 100)}% of the household's devices active today, "
            f"typically about {round(expected['device_share'] * 100)}%"
        )
    if "first_minute" in off:
        lines.append(
            f"first device online at {_clock(observed['first_minute'])}, "
            f"typically around {_clock(expected['first_minute'])}"
        )
    if "home_minutes" in off:
        lines.append(
            f"{observed['home_minutes'] / 60:.1f} h of resident time at home, "
            f"typically about {expected['home_minutes'] / 60:.1f} h"
        )
    for feature in sorted(f for f in off if f.startswith(EVENT_PREFIX)):
        lines.append(
            f"{observed[feature]:g} {_label(feature)} events by {CUTOFF_HOUR}:00, "
            f"typically about {expected[feature]:g}"
        )
    return lines


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
inv AS (  -- the devices seen in the INVENTORY_DAYS before the day: what "all devices" meant then
  SELECT d.d, COUNT(DISTINCT s.device_id) AS n
  FROM days d JOIN sess s
    ON s.start_local < CAST(d.d AS TIMESTAMP)
   AND s.end_local > CAST(d.d AS TIMESTAMP) - INTERVAL {inventory} DAY
  GROUP BY d.d),
firsts AS (  -- the first device to COME ONLINE that day (always-on gear spans midnight)
  SELECT d.d, MIN(epoch(s.start_local - CAST(d.d AS TIMESTAMP)) / 60.0) AS first_minute
  FROM days d JOIN sess s
    ON s.start_local >= CAST(d.d AS TIMESTAMP)
   AND s.start_local < CAST(d.d AS TIMESTAMP) + INTERVAL {cutoff} HOUR
  GROUP BY d.d){home_cte}
SELECT days.d, COUNT(DISTINCT act.device_id), COALESCE(firsts.first_minute, {cutoff} * 60.0),
       {home_select}, COALESCE(inv.n, 0)
FROM days JOIN ok ON ok.d = days.d
LEFT JOIN act ON act.d = days.d LEFT JOIN firsts ON firsts.d = days.d
LEFT JOIN inv ON inv.d = days.d
{home_join}
GROUP BY days.d, firsts.first_minute, inv.n{home_group} ORDER BY days.d
"""

# Person-minutes at home before the cutoff, for the people who live here (gold presence_grid joined
# to the user type silver recorded). Absent when presence was never built.
_HOME_SQL = """,
homes AS (
  SELECT g.date_local AS d, SUM(g.minutes_home) AS m
  FROM grid_users g JOIN user_types u ON u.user_id = g.user_id
  WHERE g.hour_local < {cutoff} GROUP BY 1)"""


def _add_event_counts(con, rates_file, days):
    """Add `event:<type>/<subject>/<verb>` -> the day's count up to the cutoff to each day. A stream
    is measured from the day it first appears (before that the count is unknown, not zero); after
    that a day with no events counts 0. The lake's counts have sa_data_exclusions applied."""
    if not os.path.exists(rates_file):
        return
    first = dict(
        con.execute(f"SELECT signal, MIN(date_local) FROM read_parquet('{rates_file}') GROUP BY 1")
        .fetchall()
    )
    counts = {
        (d, signal): n
        for d, signal, n in con.execute(
            f"SELECT date_local, signal, SUM(n) FROM read_parquet('{rates_file}') "
            f"WHERE hour_local < {CUTOFF_HOUR} GROUP BY 1, 2"
        ).fetchall()
    }
    for day in days:
        for signal, started in first.items():
            if day["date"] >= started:
                day[EVENT_PREFIX + signal] = float(counts.get((day["date"], signal), 0))


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
            inventory=INVENTORY_DAYS,
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
            {
                "date": d,
                "devices": n,
                "inventory": inv,
                "device_share": (n / inv) if inv >= MIN_INVENTORY else None,
                "first_minute": fm if n else None,
                "home_minutes": hm,
            }
            for d, n, fm, hm, inv in rows
        ]
        rates_file = os.path.join(lake_dir, "gold", "hourly_rates", "part-0.parquet")
        _add_event_counts(con, rates_file, days)
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
    """Walk-forward: for each day in [start, end], the day's features and statistic ("bits") scored
    on a profile fitted (and its bar calibrated) on the days before it, plus whether it clears
    that bar ("flagged"). Returns [{"date", "bits", "bar_bits", "flagged", "top": [(feature, p)]}]."""
    learner = learner or HouseholdDayLearner()
    data = load_days(lake_dir)
    out = []
    for day in data["days"]:
        if not (start <= day["date"] <= end):
            continue
        profile = learner.fit_days(data["days"], day["date"] - timedelta(days=1), data["coverage"])
        if profile is None or day["first_minute"] is None:
            continue
        local_dt = datetime.combine(day["date"], datetime.min.time()).replace(hour=CUTOFF_HOUR)
        rows = learner.score_features(profile, {**day, "local_dt": local_dt}, local_dt)
        bits = top_bits([r.probability for r in rows])
        if bits is None:
            continue
        bar = profile.params["calibration"]["bar_bits"]
        top = sorted(rows, key=lambda r: r.probability)[:TOP_K]
        out.append(
            {
                **day,
                "bits": bits,
                "bar_bits": bar,
                "flagged": bar is not None and bits >= bar,
                "top": [(r.evidence["feature"], r.probability) for r in top],
            }
        )
    return out


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    for profile in HouseholdDayLearner().fit(os.environ.get("SA_LAKE_DIR", "/lake")):
        print(profile.params)
