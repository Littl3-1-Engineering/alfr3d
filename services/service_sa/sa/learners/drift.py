"""Drift detector: has the regime behind a learned profile changed? Sixth learner family after
presence (LF-3), scalar (LF-4a), rates, device rhythm and household day (LF-4b/5a). LF-5.

Every other learner multiplies a `stability` term into its confidence, measured from how well it
predicted the recent past. That catches a bad model, not the reason it is bad. This learner looks
for the reason: a level shift in a daily feature of the series (a new job, a house move, a sensor
moved to another room), dates it, and lowers `stability` in the profiles it affects until enough
days have passed in the new regime for them to re-learn.

Model
-----
One daily feature per profiled subject: minutes at home per person (observed days), the daily mean
of a scalar series (log scale where the scalar learner uses it), the daily count of an event or
email stream (log1p). Per series a two-sided tabular CUSUM:

- A reference is the first 14 days of the current regime: median per day type (work / off) and a
  robust sigma (1.4826 x MAD of the residuals, floored at 5 % of the level, so a flat series does
  not make every wiggle an alarm). Removing the day-type mean keeps the weekday/weekend pattern
  from reading as drift.
- z = (x - reference) / sigma. S+ = max(0, S+ + z - K), S- = max(0, S- - z - K); an alarm is
  S > H. K = 0.5 and H = 5 sigma give an in-control average run length of about 465 days.
- The change is dated to where the alarm's run of positive S began, not to the alarm day. The new
  regime starts there; its first 14 days become the next reference and testing resumes after.

Output per subject: a `drift` profile (the changes found, the current reference, the CUSUM state)
and, for a change found in the last 14 days, a `drift` inference. `stability` of the profiled
learner's own row is then capped: 0.3 on the day a change starts, back to 1.0 after 28 days, and
at most 1 - 0.4 min(1, S/H) while an alarm is building. The cap is idempotent and is re-applied
after every fit, since the other learners rewrite their own stability.

Not covered here: the profiled learners hold wall-clock hour-of-day cells, so a change that only
moves *when* something happens, not how much, is not a level shift. Presence and the device
rhythm learners handle that through their own walk-forward stability.
"""

import logging
import math
import os
import statistics
from datetime import date, datetime, timedelta

import duckdb

from sa import confidence, inference_store
from sa.learners.base import Inference, Learner, Profile, utcnow
from sa.learners.scalar import subject_id_for, to_model, uses_log

logger = logging.getLogger("SADrift")

NAME = "drift"
VERSION = "1"
SIGNAL = "drift.daily"

REF_DAYS = 14
MIN_REF_DAYS = 7
MIN_DAYS = 21
CUSUM_K = 0.5
CUSUM_H = 5.0
ARL0_DAYS = 465  # in-control average run length of (K, H) on standardised data
SIGMA_FLOOR_FRACTION = 0.05
SIGMA_ABS_FLOOR = 0.05
MIN_RUN_DAYS = 7  # a level shift has to persist for a week before it counts
MIN_SHIFT_SIGMA = 1.0  # and be at least this large for the typical day of that run
Z_CLIP = 4.0  # one wild day may not carry the accumulator on its own
# Smallest sigma worth testing against, per feature: below it a flat series turns any wiggle into
# a many-sigma "shift" (a visitor with zero minutes at home every day, a counter that is always 0).
FEATURE_MIN_SIGMA = {"minutes_home": 45.0, "daily_count.log1p": 0.4}
RECENT_ALARM_DAYS = 14
RECOVERY_DAYS = 28
STABILITY_AT_CHANGE = 0.3
BUILDING_PENALTY = 0.4

MIN_SCALAR_HOURS = 12
MIN_RATE_HOURS = 20

# profiled learner -> (profile-subject family, feature)
TARGETS = {
    "presence_profile": "user",
    "stay_profile": "user",  # same daily at-home minutes: a changed routine changes stay lengths
    "scalar_baseline": "series",
    "event_rate": "stream",
}


# --- Detection (pure) ------------------------------------------------------------------------


def _reference(points, daytype_of, min_sigma=SIGMA_ABS_FLOOR):
    """({daytype: level}, pooled level, sigma) from the reference days."""
    xs = [x for _, x in points]
    pooled = statistics.median(xs)
    levels = {}
    for dt in ("work", "off"):
        vals = [x for d, x in points if daytype_of(d) == dt]
        levels[dt] = statistics.median(vals) if len(vals) >= 3 else pooled
    resid = [x - levels[daytype_of(d)] for d, x in points]
    center = statistics.median(resid)
    mad = statistics.median(abs(r - center) for r in resid)
    sigma = max(1.4826 * mad, SIGMA_FLOOR_FRACTION * max(abs(pooled), 1.0), min_sigma)
    return levels, pooled, sigma


def detect(points, daytype_of=None, min_sigma=SIGMA_ABS_FLOOR):
    """Run the CUSUM over [(date, value)], oldest first. Returns None when the series is too short,
    else {"changes": [{"start", "alarm", "direction", "shift_sigma", "days"}], "segment_start",
    "settled", "s_plus", "s_minus", "levels", "sigma", "n"}."""
    points = sorted(points)
    if len(points) < MIN_DAYS:
        return None
    daytype_of = daytype_of or (lambda d: "off" if d.weekday() >= 5 else "work")
    changes = []
    seg = 0
    while True:
        ref_pts = points[seg : seg + REF_DAYS]
        if len(ref_pts) < (REF_DAYS if not changes else MIN_REF_DAYS):
            return {
                "changes": changes,
                "segment_start": points[seg][0],
                "settled": False,
                "s_plus": 0.0,
                "s_minus": 0.0,
                "levels": None,
                "sigma": None,
                "n": len(points),
            }
        levels, pooled, sigma = _reference(ref_pts, daytype_of, min_sigma)
        s_plus = s_minus = 0.0
        run_plus = run_minus = seg + len(ref_pts)
        alarm = None
        zs = {}
        for i in range(seg + len(ref_pts), len(points)):
            d, x = points[i]
            z = (x - levels[daytype_of(d)]) / sigma
            zs[i] = z
            z = max(-Z_CLIP, min(Z_CLIP, z))
            if s_plus == 0.0:
                run_plus = i
            if s_minus == 0.0:
                run_minus = i
            s_plus = max(0.0, s_plus + z - CUSUM_K)
            s_minus = max(0.0, s_minus - z - CUSUM_K)
            if s_plus > CUSUM_H or s_minus > CUSUM_H:
                up = s_plus > CUSUM_H
                start = run_plus if up else run_minus
                run = [zs[j] for j in range(start, i + 1)]
                typical = statistics.median(run)
                if len(run) < MIN_RUN_DAYS or abs(typical) < MIN_SHIFT_SIGMA:
                    continue  # a burst or a drizzle, not a new level: keep accumulating
                changes.append(
                    {
                        "start": points[start][0],
                        "alarm": d,
                        "direction": "up" if up else "down",
                        "shift_sigma": round(typical, 2),
                        "days": i - start + 1,
                    }
                )
                alarm = start
                break
        if alarm is None:
            return {
                "changes": changes,
                "segment_start": points[seg][0],
                "settled": True,
                "s_plus": round(s_plus, 3),
                "s_minus": round(s_minus, 3),
                "levels": levels,
                "sigma": sigma,
                "n": len(points),
            }
        seg = alarm


def stability_of(result, last_day):
    """The cap this result puts on the profiled learner's stability, in (0, 1]."""
    cap = 1.0
    if result["changes"]:
        since = (last_day - result["changes"][-1]["start"]).days
        if since < RECOVERY_DAYS:
            cap = STABILITY_AT_CHANGE + (1 - STABILITY_AT_CHANGE) * max(0, since) / RECOVERY_DAYS
    building = min(1.0, max(result["s_plus"], result["s_minus"]) / CUSUM_H)
    return round(max(0.05, min(cap, 1.0 - BUILDING_PENALTY * building)), 4)


# --- The learner -----------------------------------------------------------------------------


class DriftLearner(Learner):
    name = NAME
    version = VERSION

    def fit(self, features, daytype_of=None, last_day=None):
        """features: {(target_learner, subject_type, subject_id): {"feature": str, "points":
        [(date, value)]}}. Returns [Profile] for every series long enough to test."""
        profiles = []
        for (target, subject_type, subject_id), f in features.items():
            result = detect(
                f["points"], daytype_of, FEATURE_MIN_SIGMA.get(f["feature"], SIGMA_ABS_FLOOR)
            )
            if result is None:
                continue
            last = last_day or f["points"][-1][0]
            stab = stability_of(result, last)
            changes = result["changes"]
            params = {
                "target_learner": target,
                "feature": f["feature"],
                "changes": [
                    {k: (v.isoformat() if isinstance(v, date) else v) for k, v in c.items()}
                    for c in changes
                ],
                "regime_start": result["segment_start"].isoformat(),
                "settled": result["settled"],
                "s_plus": result["s_plus"],
                "s_minus": result["s_minus"],
                "sigma": result["sigma"],
                "levels": result["levels"],
                "last_day": last.isoformat(),
                "stability_cap": stab,
            }
            profiles.append(
                Profile(
                    learner=NAME,
                    learner_version=VERSION,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    signal=SIGNAL,
                    params=params,
                    n_eff=float(result["n"]),
                    coverage=1.0,
                    source_quality=1.0,
                    stability=stab,
                    fitted_from=f["points"][0][0],
                    fitted_to=f["points"][-1][0],
                )
            )
        return profiles

    def score(self, profile, state=None, now=None):
        """A `drift` inference for a change whose alarm is recent, else None."""
        p = profile.params
        if not p["changes"]:
            return None
        change = p["changes"][-1]
        alarm = date.fromisoformat(change["alarm"])
        last = date.fromisoformat(p["last_day"])
        if (last - alarm).days > RECENT_ALARM_DAYS:
            return None
        start = date.fromisoformat(change["start"])
        terms = confidence.Confidence(confidence.sufficiency(change["days"]), 1.0, 1.0, 1.0)
        probability = round(1.0 / ARL0_DAYS, 5)
        return Inference(
            kind="drift",
            subject_type=profile.subject_type,
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=NAME,
            learner_version=VERSION,
            window_start=datetime(start.year, start.month, start.day),
            window_end=datetime(last.year, last.month, last.day),
            context={"target_learner": p["target_learner"], "feature": p["feature"]},
            observed={"direction": change["direction"], "shift_sigma": change["shift_sigma"]},
            expected={"sigma": p["sigma"], "alarm_date": change["alarm"]},
            probability=probability,
            surprise=round(-math.log2(probability), 3),
            confidence=round(terms.value, 4),
            n_eff=float(change["days"]),
            evidence={"terms": terms.as_dict(), "arl0_days": ARL0_DAYS, "changes": p["changes"]},
            expires_at=(now or utcnow()) + timedelta(days=RECENT_ALARM_DAYS),
        )


# --- Reading the lake ------------------------------------------------------------------------


def _path(lake_dir, layer, table):
    return os.path.join(lake_dir, layer, table, "part-0.parquet")


def load_features(lake_dir, wanted):
    """Daily features for the profiled subjects in `wanted` ({(learner, subject_type, subject_id)}).
    Only days the data really covers are included: observed presence days, scalar days with at
    least MIN_SCALAR_HOURS hours reported, stream days with at least MIN_RATE_HOURS live hours and
    not the day still in progress."""
    out = {}
    con = duckdb.connect()
    try:
        daily = _path(lake_dir, "gold", "daily_rhythm")
        if os.path.exists(daily):
            for uid, d, minutes in con.execute(
                f"SELECT user_id, date_local, minutes_home FROM read_parquet('{daily}') "
                f"WHERE observed ORDER BY user_id, date_local"
            ).fetchall():
                for target in ("presence_profile", "stay_profile"):
                    key = (target, "user", str(uid))
                    if key in wanted:
                        out.setdefault(key, {"feature": "minutes_home", "points": []})
                        out[key]["points"].append((d, float(minutes)))

        scalar = _path(lake_dir, "gold", "scalar_hourly")
        if os.path.exists(scalar):
            by_subject = {
                subject_id_for(k): k
                for (k,) in con.execute(
                    f"SELECT DISTINCT series_key FROM read_parquet('{scalar}')"
                ).fetchall()
            }
            for subject_id, series_key in by_subject.items():
                key = ("scalar_baseline", "series", subject_id)
                if key not in wanted:
                    continue
                rows = con.execute(
                    f"SELECT date_local, AVG(mean), COUNT(*) FROM read_parquet('{scalar}') "
                    f"WHERE series_key = ? AND mean IS NOT NULL GROUP BY date_local "
                    f"HAVING COUNT(*) >= {MIN_SCALAR_HOURS} ORDER BY date_local",
                    [series_key],
                ).fetchall()
                out[key] = {
                    "feature": "daily_mean" + (".log" if uses_log(series_key) else ""),
                    "points": [(d, to_model(series_key, float(m))) for d, m, _ in rows],
                }

        rates = _path(lake_dir, "gold", "hourly_rates")
        if os.path.exists(rates):
            horizon = con.execute(
                f"SELECT MAX(date_local) FROM read_parquet('{rates}')"
            ).fetchone()[0]
            rows = con.execute(
                f"SELECT signal, date_local, SUM(n), COUNT(DISTINCT hour_local) "
                f"FROM read_parquet('{rates}') GROUP BY signal, date_local "
                f"ORDER BY signal, date_local"
            ).fetchall()
            live = {
                d
                for (d,) in con.execute(
                    f"SELECT date_local FROM read_parquet('{rates}') GROUP BY date_local "
                    f"HAVING COUNT(DISTINCT bucket_utc) >= {MIN_RATE_HOURS}"
                ).fetchall()
            }
            for sig, d, n, _ in rows:
                key = ("event_rate", "stream", f"event:{sig}")
                if key in wanted and d in live and d != horizon:
                    out.setdefault(key, {"feature": "daily_count.log1p", "points": []})
                    out[key]["points"].append((d, math.log1p(float(n))))

        email = _path(lake_dir, "gold", "email_hourly")
        if os.path.exists(email):
            horizon = con.execute(
                f"SELECT MAX(date_local) FROM read_parquet('{email}')"
            ).fetchone()[0]
            for stream, col in (
                ("email/all", "n"),
                ("email/promotions", "n_promotions"),
                ("email/updates", "n_updates"),
            ):
                key = ("event_rate", "stream", stream)
                if key not in wanted:
                    continue
                rows = con.execute(
                    f"SELECT date_local, SUM({col}) FROM read_parquet('{email}') "
                    f"WHERE date_local < ? GROUP BY date_local "
                    f"HAVING COUNT(DISTINCT hour_local) >= {MIN_RATE_HOURS} ORDER BY date_local",
                    [horizon],
                ).fetchall()
                out[key] = {
                    "feature": "daily_count.log1p",
                    "points": [(d, math.log1p(float(n or 0))) for d, n in rows],
                }
        return out
    finally:
        con.close()


def _daytypes(lake_dir):
    path = _path(lake_dir, "silver", "day_context")
    if not os.path.exists(path):
        return None
    con = duckdb.connect()
    try:
        kinds = {
            d: ("off" if (wk or hol) else "work")
            for d, wk, hol in con.execute(
                f"SELECT date, is_weekend, is_holiday FROM read_parquet('{path}')"
            ).fetchall()
        }
    finally:
        con.close()
    return lambda d: kinds.get(d, "off" if d.weekday() >= 5 else "work")


def profiled_subjects(conn):
    """{(learner, subject_type, subject_id)} for every profile the detector can watch."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT learner, subject_type, subject_id FROM sa_profiles WHERE learner IN %s "
        "AND subject_type IN ('user', 'series', 'stream')",
        (tuple(TARGETS),),
    )
    return {(row[0], row[1], row[2]) for row in cursor.fetchall() if TARGETS[row[0]] == row[1]}


def apply_stability(conn, profiles, now_utc=None):
    """Cap `stability` in the profiled learners' own rows. Only rows whose stability is above the
    cap are touched (and re-stamped, so sa-awareness reloads them). Returns rows lowered."""
    now_utc = now_utc or utcnow()
    cursor = conn.cursor()
    lowered = 0
    for p in profiles:
        if p.stability is None or p.stability >= 1.0:
            continue
        cursor.execute(
            "UPDATE sa_profiles SET stability = %s, computed_at = %s WHERE learner = %s "
            "AND subject_type = %s AND subject_id = %s AND (stability IS NULL OR stability > %s)",
            (
                p.stability,
                now_utc,
                p.params["target_learner"],
                p.subject_type,
                p.subject_id,
                p.stability,
            ),
        )
        lowered += cursor.rowcount
    conn.commit()
    return lowered


def run_fit(lake_dir, conn, now_utc=None):
    """Run after the other learners' fits (they rewrite their own stability): detect level shifts
    in every profiled series, store the drift profiles and recent changes, cap stability."""
    now_utc = now_utc or utcnow()
    wanted = profiled_subjects(conn)
    features = load_features(lake_dir, wanted)
    learner = DriftLearner()
    profiles = learner.fit(features, daytype_of=_daytypes(lake_dir))
    if profiles:
        inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    found = [i for i in (learner.score(p, now=now_utc) for p in profiles) if i]
    for inference in found:
        inference_store.upsert_inference(conn, inference)
    lowered = apply_stability(conn, profiles, now_utc)
    return {
        "watched": len(features),
        "profiles": len(profiles),
        "removed": removed,
        "changes": len(found),
        "stability_lowered": lowered,
    }
