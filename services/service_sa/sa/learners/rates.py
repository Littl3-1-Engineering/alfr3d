"""Event-stream rate learner: is this many events (messages, track plays, notifications, ...) in
this window unusual for this stream, at this time? Third learner family after presence (LF-3) and
scalar series (LF-4a).

Streams
-------
- hourly: household events by `event_type/subject_type/verb` (gold `hourly_rates`, zero-filled here
  against the lake horizon) and email volume by category (gold `email_hourly`).
- daily:  per-sender message counts (gold `sender_daily`): "this sender is far busier than usual".

Model
-----
Counts are over-dispersed (a chatty hour comes with chatty neighbours), so a plain Poisson would
cry wolf. Each cell (day type x hour for hourly streams, one cell for daily ones) holds a
recency-weighted Gamma-Poisson posterior shrunk towards its parent (hour-of-day over both day
types, itself shrunk towards the stream's overall rate), plus a per-stream dispersion phi from the
method of moments. The predictive distribution of a window's count is negative binomial with mean m
and r = 1 / (phi + 1/a), where a is the posterior shape (so a thinly observed cell is wider).

A deviation is the upper tail P(N >= n) for an unusually high count, or the lower tail P(N <= n)
for an unusually quiet window, both only when the expectation is large enough for "quiet" to mean
something. Probability, surprise bits and the shared confidence go in the Inference.

Confidence terms: sufficiency from the cell's effective days, coverage from how much of the last
week the whole event log was alive for, source quality 1.0 for system-written streams and 0.9 for
email (a polled API), stability from a change in the stream's volume between the last week and the
fortnight before it.
"""

import logging
import math
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb

from sa import confidence, inference_store
from sa.learners.base import Inference, Learner, Profile, utcnow
from sa.learners.scalar import subject_id_for

logger = logging.getLogger("SARates")

NAME = "event_rate"
VERSION = "1"
SIGNAL = "rate.count"

HALF_LIFE_DAYS = 28.0
PRIOR_STRENGTH_HOURS = 6.0  # cell shrinks to its parent with the weight of this many days
PARENT_STRENGTH_HOURS = 24.0  # hour-of-day shrinks to the stream's overall rate
MIN_EVENTS = 30
MIN_ACTIVE_DAYS = 7
MIN_DAYS_OF_HISTORY = 7
PHI_FLOOR = 0.05
PHI_CEILING = 25.0

# Event streams worth modelling. The firehose of free-text `info/-/-`, `audio/-/-` and
# `personality_state` rows is the system talking to itself, not the household doing something.
EVENT_SIGNALS = (
    "audio/track/play_start",
    "notification/sender/messaged",
    "notification/sender/called",
    "info/user/came_online",
    "warning/user/went_offline",
    "routine/routine/executed",
    "iot/device/turned_on",
    "iot/device/turned_off",
    "iot/device/set",
    "presence/user/entered_area",
)
EMAIL_STREAMS = (
    ("email/all", "n"),
    ("email/promotions", "n_promotions"),
    ("email/updates", "n_updates"),
)
EMAIL_QUALITY = 0.9

# Sender streams
SENDER_MIN_ACTIVE_DAYS = 8
SENDER_MIN_MESSAGES = 20
SENDER_MAX_STREAMS = 60
SENDER_SCORE_DAYS = 3

# Scoring
P_FLAG = 1e-4  # tail probability at or below which a window is flagged
MIN_EXCESS = 3  # a high count must exceed the expectation by at least this many events
MIN_EXPECTED_FOR_LOW = 4.0  # a "quiet" flag needs at least this many events expected
RECENT_SCORE_HOURS = 48
COVERAGE_HOURS = 168
STABILITY_UNKNOWN = 0.5


# --- Negative binomial -----------------------------------------------------------------------


def nb_logpmf(k, r, m):
    """log P(N = k) for a negative binomial with mean m and size r."""
    if m <= 0:
        return 0.0 if k == 0 else -math.inf
    p = r / (r + m)
    return (
        math.lgamma(k + r)
        - math.lgamma(r)
        - math.lgamma(k + 1)
        + r * math.log(p)
        + k * math.log1p(-p)
    )


def nb_upper(k, r, m):
    """P(N >= k). Summed upward when k is in the upper tail so tiny tails don't cancel."""
    if k <= 0:
        return 1.0
    if m <= 0:
        return 0.0
    if k > m:
        total, i = 0.0, k
        while i < k + 5000:
            term = math.exp(nb_logpmf(i, r, m))
            total += term
            if term < 1e-18 * max(total, 1e-300) and i > k + 5:
                break
            i += 1
        return min(1.0, total)
    return max(0.0, 1.0 - sum(math.exp(nb_logpmf(i, r, m)) for i in range(k)))


def nb_lower(k, r, m):
    """P(N <= k)."""
    if k < 0:
        return 0.0
    return min(1.0, sum(math.exp(nb_logpmf(i, r, m)) for i in range(k + 1)))


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# --- Fitting ---------------------------------------------------------------------------------


def _weight(day, ref):
    return 0.5 ** (max(0, (ref - day).days) / HALF_LIFE_DAYS)


def fit_stream(key, window, points, ref, daytypes, coverage=1.0, quality=1.0):
    """Profile for one stream, or None. points: dicts with date, hour (0 for daily streams), n,
    one per window including the zeros, up to but excluding the first unobserved window."""
    points = [p for p in points if p["date"] <= ref]
    total = sum(p["n"] for p in points)
    active_days = len({p["date"] for p in points if p["n"] > 0})
    span_days = len({p["date"] for p in points})
    if total < (MIN_EVENTS if window == "hour" else SENDER_MIN_MESSAGES):
        return None
    if active_days < (MIN_ACTIVE_DAYS if window == "hour" else SENDER_MIN_ACTIVE_DAYS):
        return None
    if span_days < MIN_DAYS_OF_HISTORY:
        return None

    kinds = ("work", "off") if window == "hour" else ("all",)
    slots = 24 if window == "hour" else 1

    def kind_of(p):
        return daytypes.get(p["date"], "work") if window == "hour" else "all"

    sums = {k: [0.0] * slots for k in kinds}  # sum w*n
    wts = {k: [0.0] * slots for k in kinds}  # sum w
    hour_sum, hour_w = [0.0] * slots, [0.0] * slots
    all_sum = all_w = 0.0
    for p in points:
        w = _weight(p["date"], ref)
        k, h = kind_of(p), p["hour"] if window == "hour" else 0
        sums[k][h] += w * p["n"]
        wts[k][h] += w
        hour_sum[h] += w * p["n"]
        hour_w[h] += w
        all_sum += w * p["n"]
        all_w += w
    overall = all_sum / all_w if all_w else 0.0
    parent = [
        (PARENT_STRENGTH_HOURS * overall + hour_sum[h]) / (PARENT_STRENGTH_HOURS + hour_w[h])
        for h in range(slots)
    ]
    cells, cell_w = {}, {}
    for k in kinds:
        cells[k] = [
            (PRIOR_STRENGTH_HOURS * parent[h] + sums[k][h]) / (PRIOR_STRENGTH_HOURS + wts[k][h])
            for h in range(slots)
        ]
        cell_w[k] = [PRIOR_STRENGTH_HOURS + wts[k][h] for h in range(slots)]

    # Dispersion by the method of moments against the cell means.
    num = den = 0.0
    for p in points:
        w = _weight(p["date"], ref)
        m = cells[kind_of(p)][p["hour"] if window == "hour" else 0]
        num += w * ((p["n"] - m) ** 2 - m)
        den += w * m * m
    phi = _clamp(num / den if den > 0 else PHI_FLOOR, PHI_FLOOR, PHI_CEILING)

    # Stability: volume of the last 7 days vs the 14 before them.
    recent_cut = ref - timedelta(days=6)
    prior_cut = recent_cut - timedelta(days=14)
    recent = [p["n"] for p in points if p["date"] >= recent_cut]
    prior = [p["n"] for p in points if prior_cut <= p["date"] < recent_cut]
    if len({p["date"] for p in points if p["date"] >= recent_cut}) >= 5 and len(prior) >= 5 * (
        24 if window == "hour" else 1
    ):
        r_recent, r_prior = sum(recent) / len(recent), sum(prior) / len(prior)
        change = abs(math.log((r_recent + 0.01) / (r_prior + 0.01)))
        stability = 1.0 / (1.0 + change)
    else:
        stability = STABILITY_UNKNOWN

    return Profile(
        learner=NAME,
        learner_version=VERSION,
        subject_type="stream" if window == "hour" else "sender",
        subject_id=subject_id_for(key),
        signal=SIGNAL,
        params={
            "stream": key,
            "window": window,
            "cells": {k: [round(x, 5) for x in v] for k, v in cells.items()},
            "cell_weight": {k: [round(x, 3) for x in v] for k, v in cell_w.items()},
            "phi": round(phi, 4),
            "overall_rate": round(overall, 5),
            "total_events": total,
        },
        n_eff=round(sum(wts[k][h] for k in kinds for h in range(slots)) / slots / len(kinds), 3),
        coverage=round(_clamp(coverage), 4),
        source_quality=quality,
        stability=round(stability, 4),
        fitted_from=min(p["date"] for p in points),
        fitted_to=ref,
    )


class RateLearner(Learner):
    name = NAME
    version = VERSION

    def expected(self, params, kind, hour):
        """(mean, r) of the negative-binomial predictive for one window."""
        cells = params["cells"]
        kind = kind if kind in cells else next(iter(cells))
        m = cells[kind][hour]
        a = max(m * params["cell_weight"][kind][hour], 1e-6)  # Gamma posterior shape
        r = 1.0 / (params["phi"] + 1.0 / a)
        return m, r

    def tail(self, profile, state):
        """(direction, p, mean) for an observed count, or None when it is unremarkable by
        construction (too small a gap or a too-small expectation)."""
        m, r = self.expected(profile.params, state.get("daytype", "work"), state.get("hour", 0))
        n = int(state["count"])
        if n >= m + MIN_EXCESS:
            return "high", nb_upper(n, r, m), m
        if m >= MIN_EXPECTED_FOR_LOW and n < m:
            return "low", nb_lower(n, r, m), m
        return None

    def score(self, profile, state, now):
        """A deviation Inference if the tail probability is at or below P_FLAG, else None.
        state: {"count", "hour", "daytype", "window_start"}."""
        t = self.tail(profile, state)
        if t is None:
            return None
        direction, p, mean = t
        if p > P_FLAG:
            return None
        p = max(p, 1e-12)
        terms = confidence.Confidence(
            confidence.sufficiency(profile.n_eff),
            profile.coverage,
            profile.source_quality,
            profile.stability,
        )
        window = profile.params["window"]
        start = state["window_start"]
        return Inference(
            kind="deviation",
            subject_type=profile.subject_type,
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=start,
            window_end=start + (timedelta(hours=1) if window == "hour" else timedelta(days=1)),
            context={"stream": profile.params["stream"], "hour_local": state.get("hour")},
            observed={"count": int(state["count"]), "direction": direction},
            expected={"mean": round(mean, 3), "phi": profile.params["phi"]},
            probability=round(p, 12),
            surprise=round(-math.log2(p), 3),
            confidence=round(terms.value, 4),
            n_eff=profile.n_eff,
            evidence={"terms": terms.as_dict(), "stream": profile.params["stream"]},
            expires_at=(now or utcnow()) + timedelta(hours=12),
        )

    def fit(self, lake_dir, ref=None):
        data = load_streams(lake_dir)
        ref = ref or data["ref"]
        profiles = []
        for key, s in sorted(data["streams"].items()):
            profile = fit_stream(
                key, s["window"], s["points"], ref, data["daytypes"], data["coverage"], s["quality"]
            )
            if profile is not None:
                profiles.append(profile)
        logger.info(f"rates: fitted {len(profiles)} streams as of {ref}")
        return profiles


# --- Reading the lake --------------------------------------------------------------------------


def _local_to_utc(tz, d, hour):
    return (
        datetime.combine(d, datetime.min.time())
        .replace(hour=hour, tzinfo=tz)
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )


def load_streams(lake_dir, tz_name=None):
    """{"streams": {key: {"window", "points", "quality"}}, "daytypes", "ref", "horizon",
    "coverage"}. Event streams are zero-filled from their first local day to the event-log
    horizon; the hour still in progress at the horizon is not a window yet."""
    from sa import silver

    tz = ZoneInfo(tz_name or silver.TIMEZONE)
    out = {"streams": {}, "daytypes": {}, "ref": None, "horizon": None, "coverage": 1.0}
    con = duckdb.connect()
    try:
        path = lambda layer, t: os.path.join(lake_dir, layer, t, "part-0.parquet")  # noqa: E731
        ctx, rates = path("silver", "day_context"), path("gold", "hourly_rates")
        senders_file = path("gold", "sender_daily")
        if os.path.exists(ctx):
            for d, wk, hol in con.execute(
                f"SELECT date, is_weekend, is_holiday FROM read_parquet('{ctx}')"
            ).fetchall():
                out["daytypes"][d] = "off" if (wk or hol) else "work"

        horizon = None
        if os.path.exists(rates):
            horizon = con.execute(
                f"SELECT MAX(bucket_utc) FROM read_parquet('{rates}')"
            ).fetchone()[0]
            alive = {
                b
                for (b,) in con.execute(
                    f"SELECT DISTINCT bucket_utc FROM read_parquet('{rates}')"
                ).fetchall()
            }
            if horizon:
                window = [horizon - timedelta(hours=i) for i in range(1, COVERAGE_HOURS + 1)]
                out["coverage"] = sum(1 for b in window if b in alive) / COVERAGE_HOURS
            rows = con.execute(
                f"SELECT signal, date_local, hour_local, n FROM read_parquet('{rates}') "
                f"WHERE signal IN ({','.join('?' * len(EVENT_SIGNALS))})",
                list(EVENT_SIGNALS),
            ).fetchall()
            by_signal = {}
            for sig, d, h, n in rows:
                by_signal.setdefault(sig, {})[(d, h)] = n
            for sig, cells in by_signal.items():
                out["streams"][f"event:{sig}"] = {
                    "window": "hour",
                    "points": _dense(cells, tz, horizon),
                    "quality": 1.0,
                }
        if os.path.exists(path("gold", "email_hourly")):
            cols = ", ".join(c for _, c in EMAIL_STREAMS)
            email = con.execute(
                f"SELECT date_local, hour_local, bucket_utc, {cols} "
                f"FROM read_parquet('{path('gold', 'email_hourly')}') ORDER BY bucket_utc"
            ).fetchall()
            for i, (name, _col) in enumerate(EMAIL_STREAMS):
                cells = {(r[0], r[1]): int(r[3 + i] or 0) for r in email}
                out["streams"][name] = {
                    "window": "hour",
                    "points": _dense(cells, tz, email[-1][2]),
                    "quality": EMAIL_QUALITY,
                }
        if os.path.exists(senders_file) and horizon:
            last_full_day = (horizon - timedelta(hours=1)).date() - timedelta(days=1)
            rows = con.execute(
                f"SELECT source, sender, date_local, n FROM read_parquet('{senders_file}')"
            ).fetchall()
            senders = {}
            for src, sender, d, n in rows:
                if sender:
                    senders.setdefault((src, sender), {})[d] = n
            ranked = sorted(senders.items(), key=lambda kv: -sum(kv[1].values()))
            for (src, sender), days in ranked[:SENDER_MAX_STREAMS]:
                first = min(days)
                points, d = [], first
                while d <= last_full_day:
                    points.append({"date": d, "hour": 0, "n": days.get(d, 0), "t": None})
                    d += timedelta(days=1)
                out["streams"][f"sender:{src}:{sender}"] = {
                    "window": "day",
                    "points": points,
                    "quality": EMAIL_QUALITY if src == "gmail" else 1.0,
                }
        out["horizon"] = horizon
        dates = [p["date"] for s in out["streams"].values() for p in s["points"]]
        out["ref"] = max(dates) if dates else None
        return out
    finally:
        con.close()


def _dense(cells, tz, horizon):
    """Zero-filled hourly points from the first populated local day through the last completed
    hour before `horizon` (naive UTC)."""
    if not cells or horizon is None:
        return []
    first = min(d for d, _ in cells)
    last = horizon.date() + timedelta(days=1)
    points, d = [], first
    horizon_hour = horizon.replace(minute=0, second=0, microsecond=0)
    while d <= last:
        for h in range(24):
            t = _local_to_utc(tz, d, h)
            if t >= horizon_hour:
                return points
            points.append({"date": d, "hour": h, "n": cells.get((d, h), 0), "t": t})
        d += timedelta(days=1)
    return points


# --- Nightly job, backtest -----------------------------------------------------------------------


def _scored_windows(profile, points, daytypes, learner, since_date=None, on_dates=None):
    """Yield (point, inference-or-None) for the chosen windows."""
    for p in points:
        if since_date and p["date"] < since_date:
            continue
        if on_dates and p["date"] not in on_dates:
            continue
        state = {
            "count": p["n"],
            "hour": p["hour"],
            "daytype": daytypes.get(p["date"], "work"),
            "window_start": p["t"] or datetime.combine(p["date"], datetime.min.time()),
        }
        yield p, learner.score(profile, state, p["t"] or utcnow())


def detect_recent(lake_dir, learner=None, now_utc=None):
    """Deviations in the last RECENT_SCORE_HOURS hours (event/email streams) and the last
    SENDER_SCORE_DAYS days (sender streams), each against a profile fitted on the data before
    that window so a window never explains itself."""
    learner = learner or RateLearner()
    data = load_streams(lake_dir)
    found = []
    if not data["ref"]:
        return found
    for key, s in sorted(data["streams"].items()):
        points = s["points"]
        if not points:
            continue
        if s["window"] == "hour":
            cutoff_t = points[-1]["t"] - timedelta(hours=RECENT_SCORE_HOURS - 1)
            cut_date = cutoff_t.date() - timedelta(days=1)
            profile = fit_stream(
                key,
                "hour",
                [p for p in points if p["t"] < cutoff_t],
                cut_date + timedelta(days=1),
                data["daytypes"],
                data["coverage"],
                s["quality"],
            )
            targets = [p for p in points if p["t"] >= cutoff_t]
        else:
            cutoff = points[-1]["date"] - timedelta(days=SENDER_SCORE_DAYS - 1)
            profile = fit_stream(
                key,
                "day",
                [p for p in points if p["date"] < cutoff],
                cutoff - timedelta(days=1),
                data["daytypes"],
                data["coverage"],
                s["quality"],
            )
            targets = [p for p in points if p["date"] >= cutoff]
        if profile is None:
            continue
        for p in targets:
            state = {
                "count": p["n"],
                "hour": p["hour"],
                "daytype": data["daytypes"].get(p["date"], "work"),
                "window_start": p["t"] or datetime.combine(p["date"], datetime.min.time()),
            }
            inference = learner.score(profile, state, now_utc)
            if inference is not None:
                found.append(inference)
    return found


def backtest(lake_dir, key, start, end, learner=None):
    """Walk-forward: [{"date","hour","n","p","dir","mean"}] for every window in [start, end],
    each day scored with a profile fitted on the days before it."""
    learner = learner or RateLearner()
    data = load_streams(lake_dir)
    s = data["streams"].get(key)
    out = []
    if not s:
        return out
    day = start
    while day <= end:
        profile = fit_stream(
            key,
            s["window"],
            [p for p in s["points"] if p["date"] < day],
            day - timedelta(days=1),
            data["daytypes"],
            data["coverage"],
            s["quality"],
        )
        if profile is not None:
            for p in (q for q in s["points"] if q["date"] == day):
                t = learner.tail(
                    profile,
                    {
                        "count": p["n"],
                        "hour": p["hour"],
                        "daytype": data["daytypes"].get(day, "work"),
                    },
                )
                out.append(
                    {
                        "date": day,
                        "hour": p["hour"],
                        "n": p["n"],
                        "dir": t[0] if t else None,
                        "p": t[1] if t else None,
                        "mean": (
                            t[2] if t else learner.expected(profile.params, "work", p["hour"])[0]
                        ),
                    }
                )
        day += timedelta(days=1)
    return out


def run_fit(lake_dir, conn, now_utc=None):
    """The nightly job: fit every eligible stream, store profiles and recent deviations."""
    learner = RateLearner()
    profiles = learner.fit(lake_dir)
    if not profiles:
        return {"profiles": 0, "removed": 0, "deviations": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    found = detect_recent(lake_dir, learner, now_utc)
    for inference in found:
        inference_store.upsert_inference(conn, inference)
    return {"profiles": len(profiles), "removed": removed, "deviations": len(found)}


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    lake = os.environ.get("SA_LAKE_DIR", "/lake")
    for profile in RateLearner().fit(lake):
        print(
            f"{profile.params['stream'][:60]:60s} phi={profile.params['phi']:<7} "
            f"rate={profile.params['overall_rate']:<8} n_eff={profile.n_eff:<7} "
            f"stab={profile.stability} cov={profile.coverage}"
        )
