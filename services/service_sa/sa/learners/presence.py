"""Presence learner: how likely is each person to be home at this weekday and hour (LF-3,
todo/sa/todo_lf3_presence_learner.md).

It answers the question that started the SA restructure: Athos is normally home 9-5 on weekdays;
today he wasn't; nothing noticed. It learns P(home | person, weekday, hour) from the gold
`presence_grid` and scores the present against it, with a probability and a confidence.

Model
-----
Each observed hour contributes a fractional success f = minutes_home / 60 (0 = away all hour,
1 = home all hour), weighted by recency: w = 0.5 ** (age_days / HALF_LIFE_DAYS), a 3-week
half-life, so a habit that changed a month ago counts less than one that changed yesterday.
Counts are pooled in three levels so a sparse cell borrows strength from a denser one:

    overall mean m0                                  (all of the person's observed hours)
      -> (weekday|offday, hour)                       prior strength DAYTYPE_PRIOR_STRENGTH
        -> (day of week, hour)                         prior strength DOW_PRIOR_STRENGTH

    p_cell = (S + k * p_parent) / (W + k)        S = sum(w*f), W = sum(w), k = prior strength

That is the posterior mean of a Beta-Binomial whose prior is "k pseudo-observations at the parent
level's rate". With no data a cell returns its parent; with plenty it returns its own history.
Ontario statutory holidays count as `offday` and are kept out of the day-of-week cells, so a
Monday holiday doesn't teach the model that Mondays are quiet.

Visitors are handled by the same model: a guest with little history gets a profile whose
sufficiency is low (see sa/confidence.py), so it stays quiet until it has seen enough of them.

Scoring
-------
The observed state is binary: home or away (the household's `user.state`, which is logged from
the phone). The probability the model gave to what actually happened is p if home, else 1 - p;
surprise = -log2 of that, in bits. A deviation is emitted when surprise >= MIN_SURPRISE_BITS and,
for an absence, the person has been gone at least MIN_AWAY_MINUTES: phones nap for ~30 minutes
without anyone leaving (see sa/silver.py), so a shorter absence is not evidence of anything.

Confidence is sa/confidence.py's product of four terms. Three are properties of the profile
(coverage of the collector, quality of the phone signal, stability of recent predictions) and one
of the cell (how much history backs it).

Walk-forward honesty
--------------------
`stability` is measured by predicting the recent past with a model fitted only on data before it
(no leakage): the error over the last 14 days vs. the 14 before that. `replay`/`backtest` do the
same for any past moment, which is how the thresholds below were chosen against real history
instead of guessed.
"""

import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import duckdb

from sa import confidence, inference_store, silver
from sa.learners.base import Inference, Learner, Profile, utcnow

logger = logging.getLogger("SAPresence")

NAME = "presence_profile"
VERSION = "1"
SIGNAL = "presence.home"

# --- Model ---------------------------------------------------------------------------------
# Chosen by walk-forward log-loss on the household's real history (2026-10-10), scored on two
# disjoint windows (Aug 17-Sep 13, Sep 14-Oct 9) for the three residents: a 3-week memory beat the
# planned 8 weeks (0.404 vs 0.425 mean log-loss), a stronger day-of-week prior beat a weak one
# (the per-weekday cells overfit when pulled sharply), and a weak daytype prior was best. The gain
# is modest and the optimum sat at the edge of the grid, so treat these as "good enough and
# measured", not tuned to a decimal.
HALF_LIFE_DAYS = 21.0
DAYTYPE_PRIOR_STRENGTH = 2.0
DOW_PRIOR_STRENGTH = 8.0
# Fewer observed hours than this (3 days) and a person gets no profile at all.
MIN_OBSERVED_HOURS = 72

# --- Confidence terms ----------------------------------------------------------------------
COVERAGE_WINDOW_DAYS = 14
QUALITY_WINDOW_DAYS = 28
# A phone on the network is sighted roughly every 64 s: ~0.94 sightings per minute present.
# Density below that means a phone that sleeps its radio, which makes presence harder to see.
EXPECTED_SIGHTING_DENSITY = 0.9
QUALITY_FLOOR = 0.3
STABILITY_WINDOW_DAYS = 14
# How much the recent prediction error may exceed the error before it before stability hits 0.
STABILITY_SCALE = 0.25
# Used when there isn't enough history to measure stability at all: a deliberately middling value,
# not 1.0, because "unknown" must not read as "certain".
STABILITY_UNKNOWN = 0.5
MIN_STABILITY_ROWS = 24

# --- Scoring -------------------------------------------------------------------------------
MIN_SURPRISE_BITS = 3.0  # the observed state had <= 12.5% probability
MIN_AWAY_MINUTES = 60
# The lowest confidence at which a deviation becomes a CARD (it is always recorded as an
# inference). Confidence is a product of four terms, so it clusters low: over the backtest its
# median was 0.31-0.35 and its maximum ~0.5 for each resident. 0.3 was chosen so a resident gets
# roughly one card-day every one to two weeks (0.65/week at 3.0 bits) and the days it picks for
# Athos are the genuine absences (09-18, 09-26, 10-07, 10-08, 10-09). It is a calibrated cut, not
# a probability: the surprise does most of the discriminating.
MIN_CARD_CONFIDENCE = 0.3
# The household's user.state goes offline ~31 minutes after the last sighting.
LIVE_OFFLINE_LAG_MINUTES = 31


@lru_cache(maxsize=None)
def _holidays(year):
    return silver.ontario_holidays(year)


def is_offday(day):
    """Weekend or Ontario statutory holiday: the days that follow the weekend's routine."""
    return day.weekday() >= 5 or day in _holidays(day.year)


def _daytype(day):
    return "offday" if is_offday(day) else "weekday"


def _accumulate(rows, ref):
    """Recency-weighted fractional counts. rows: (date, hour, dow, minutes_home) for observed
    hours only. Returns overall [S, W], {(daytype, hour): [S, W]}, {(dow, hour): [S, W]}."""
    overall = [0.0, 0.0]
    by_daytype, by_dow = {}, {}
    for day, hour, dow, minutes in rows:
        age = (ref - day).days
        if age < 0:
            continue
        w = 0.5 ** (age / HALF_LIFE_DAYS)
        f = min(1.0, max(0.0, minutes / 60.0))
        overall[0] += w * f
        overall[1] += w
        cell = by_daytype.setdefault((_daytype(day), hour), [0.0, 0.0])
        cell[0] += w * f
        cell[1] += w
        if day not in _holidays(day.year):
            # Holidays stay out of the day-of-week cells (they only feed the offday level), so a
            # Monday holiday doesn't teach the model that Mondays are quiet.
            dow_cell = by_dow.setdefault((dow, hour), [0.0, 0.0])
            dow_cell[0] += w * f
            dow_cell[1] += w
    return overall, by_daytype, by_dow


def fit_cells(rows, ref):
    """The pooled model as plain lists (JSON-serialisable). `ref` is the last day included."""
    overall, by_daytype, by_dow = _accumulate(rows, ref)
    m0 = overall[0] / overall[1] if overall[1] > 0 else 0.5
    p_dt, w_dt = {}, {}
    for kind in ("weekday", "offday"):
        p_dt[kind], w_dt[kind] = [], []
        for hour in range(24):
            s, w = by_daytype.get((kind, hour), (0.0, 0.0))
            p_dt[kind].append((s + DAYTYPE_PRIOR_STRENGTH * m0) / (w + DAYTYPE_PRIOR_STRENGTH))
            w_dt[kind].append(w)
    p_dow, w_dow = [], []
    for dow in range(7):
        kind = "offday" if dow >= 5 else "weekday"
        p_row, w_row = [], []
        for hour in range(24):
            s, w = by_dow.get((dow, hour), (0.0, 0.0))
            parent = p_dt[kind][hour]
            p_row.append((s + DOW_PRIOR_STRENGTH * parent) / (w + DOW_PRIOR_STRENGTH))
            w_row.append(w)
        p_dow.append(p_row)
        w_dow.append(w_row)
    return {"m0": m0, "p_dt": p_dt, "w_dt": w_dt, "p_dow": p_dow, "w_dow": w_dow}


def cell(cells, day, hour):
    """(P(home), weight behind it) for a local date and hour. A holiday uses the offday level."""
    if day in _holidays(day.year):
        return cells["p_dt"]["offday"][hour], cells["w_dt"]["offday"][hour]
    return cells["p_dow"][day.weekday()][hour], cells["w_dow"][day.weekday()][hour]


def _mean_abs_error(rows, cells, start, end):
    """Mean |f - p| over observed hours with start <= date < end, and how many there were."""
    total, count = 0.0, 0
    for day, hour, _dow, minutes in rows:
        if start <= day < end:
            p, _w = cell(cells, day, hour)
            total += abs(min(1.0, max(0.0, minutes / 60.0)) - p)
            count += 1
    return (total / count if count else None), count


def stability_of(rows, ref):
    """How well a model fitted without the last STABILITY_WINDOW_DAYS predicted them, vs. how well
    one fitted without the 14 before predicted those. Returns (stability, detail). 1.0 means the
    recent past was no harder to predict than the past before it; it falls to 0 as the recent error
    exceeds the earlier one by STABILITY_SCALE. A person whose pattern changed recently is exactly
    who this catches: the old baseline is no longer a safe thing to call 'unusual' against."""
    w = STABILITY_WINDOW_DAYS
    recent_start, prior_start = ref - timedelta(days=w - 1), ref - timedelta(days=2 * w - 1)
    end = ref + timedelta(days=1)
    recent_model = fit_cells(
        [r for r in rows if r[0] < recent_start], recent_start - timedelta(days=1)
    )
    prior_model = fit_cells(
        [r for r in rows if r[0] < prior_start], prior_start - timedelta(days=1)
    )
    e_recent, n_recent = _mean_abs_error(rows, recent_model, recent_start, end)
    e_prior, n_prior = _mean_abs_error(rows, prior_model, prior_start, recent_start)
    detail = {
        "error_recent": e_recent,
        "error_prior": e_prior,
        "n_recent": n_recent,
        "n_prior": n_prior,
    }
    if n_recent < MIN_STABILITY_ROWS or n_prior < MIN_STABILITY_ROWS:
        detail["note"] = "not enough history to measure"
        return STABILITY_UNKNOWN, detail
    worse = max(0.0, e_recent - e_prior)
    return max(0.0, 1.0 - worse / STABILITY_SCALE), detail


def coverage_of(all_rows, ref):
    """Share of the last COVERAGE_WINDOW_DAYS' hours (within the person's own span) in which the
    collector was running at normal volume."""
    start = ref - timedelta(days=COVERAGE_WINDOW_DAYS - 1)
    window = [r for r in all_rows if start <= r[0] <= ref]
    if not window:
        return 0.0
    return sum(1 for r in window if r[4]) / len(window)


def source_quality_of(intervals, ref):
    """Sightings per minute present over the last QUALITY_WINDOW_DAYS, against the density a
    steadily connected phone produces. intervals: (start_utc, end_utc, sightings)."""
    cutoff = datetime.combine(ref - timedelta(days=QUALITY_WINDOW_DAYS), datetime.min.time())
    sightings = minutes = 0.0
    for start, end, n in intervals:
        if end >= cutoff:
            sightings += n
            minutes += (end - start).total_seconds() / 60.0 + 1.0
    if minutes <= 0:
        return QUALITY_FLOOR
    return max(QUALITY_FLOOR, min(1.0, (sightings / minutes) / EXPECTED_SIGHTING_DENSITY))


class PresenceLearner(Learner):
    name = NAME
    version = VERSION

    def fit_user(self, user_id, username, all_rows, intervals, ref):
        """Profile for one person, or None if they have too little observed history.
        all_rows: (date, hour, dow, minutes_home, observed); intervals: (start, end, sightings)."""
        observed = [(d, h, dw, m) for d, h, dw, m, ok in all_rows if ok and d <= ref]
        if len(observed) < MIN_OBSERVED_HOURS:
            return None
        cells = fit_cells(observed, ref)
        stability, detail = stability_of(observed, ref)
        params = {
            "m0": round(cells["m0"], 4),
            "p_dow": [[round(p, 4) for p in row] for row in cells["p_dow"]],
            "w_dow": [[round(w, 3) for w in row] for row in cells["w_dow"]],
            "p_daytype": {k: [round(p, 4) for p in v] for k, v in cells["p_dt"].items()},
            "w_daytype": {k: [round(w, 3) for w in v] for k, v in cells["w_dt"].items()},
            "username": username,
            "half_life_days": HALF_LIFE_DAYS,
            "stability_detail": {
                k: (round(v, 4) if isinstance(v, float) else v) for k, v in detail.items()
            },
        }
        return Profile(
            learner=self.name,
            learner_version=self.version,
            subject_type="user",
            subject_id=user_id,
            signal=SIGNAL,
            params=params,
            n_eff=round(sum(sum(row) for row in cells["w_dow"]), 3),
            coverage=round(coverage_of(all_rows, ref), 4),
            source_quality=round(source_quality_of(intervals, ref), 4),
            stability=round(stability, 4),
            fitted_from=min(d for d, *_ in observed),
            fitted_to=ref,
        )

    def fit(self, lake_dir, ref=None, user_ids=None):
        """Profiles for everyone in the gold layer. `ref` defaults to the data horizon."""
        grid, intervals, users = load_gold(lake_dir)
        if not grid:
            return []
        ref = ref or max(r[0] for rows in grid.values() for r in rows)
        profiles = []
        for user_id, rows in sorted(grid.items()):
            if user_ids and user_id not in user_ids:
                continue
            profile = self.fit_user(
                user_id, users[user_id][0], rows, intervals.get(user_id, []), ref
            )
            if profile is not None:
                profiles.append(profile)
        logger.info(f"presence: fitted {len(profiles)} profile(s) as of {ref}")
        return profiles

    # --- scoring ---------------------------------------------------------------------------

    def _terms(self, profile, weight):
        return confidence.Confidence(
            confidence.sufficiency(weight),
            profile.coverage,
            profile.source_quality,
            profile.stability,
        )

    def score(self, profile, state, now):
        """A deviation Inference if the observed state was improbable under the profile, else
        None. state: {"home": bool, "away_minutes": float|None, "local_dt": naive local datetime}.
        `now` is the naive UTC datetime of the observation."""
        cells = cells_from_params(profile.params)
        local_dt = state["local_dt"]
        day, hour = local_dt.date(), local_dt.hour
        p_home, weight = cell(cells, day, hour)
        home = bool(state["home"])
        p_observed = min(1.0, max(1e-6, p_home if home else 1.0 - p_home))
        surprise = -math.log2(p_observed)
        if surprise < MIN_SURPRISE_BITS:
            return None
        away_minutes = state.get("away_minutes")
        if not home:
            if away_minutes is None or away_minutes < MIN_AWAY_MINUTES:
                return None
            window_start = now - timedelta(minutes=away_minutes)  # the last sighting
        else:
            window_start = now.replace(minute=0, second=0, microsecond=0)
        terms = self._terms(profile, weight)
        return Inference(
            kind="deviation",
            subject_type="user",
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=window_start.replace(microsecond=0),
            window_end=now.replace(microsecond=0),
            context={
                "dow": day.weekday(),
                "hour_local": hour,
                "daytype": _daytype(day),
                "holiday": day in _holidays(day.year),
            },
            observed={"state": "home" if home else "away", "away_minutes": away_minutes},
            expected={"p_home": round(p_home, 4)},
            probability=round(p_observed, 6),  # 4 places would store a 1-in-10,000 event as 0
            surprise=round(surprise, 3),
            confidence=round(terms.value, 4),
            n_eff=round(weight, 3),
            evidence={"terms": terms.as_dict(), "username": profile.params.get("username")},
            expires_at=now + timedelta(hours=6),
        )

    def predict(self, profile, now_utc, tz):
        """P(home) for each of the next 24 local hours, as one prediction Inference."""
        cells = cells_from_params(profile.params)
        zone = ZoneInfo(tz)
        local_now = now_utc.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)
        first = local_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        hours, weights = [], []
        for i in range(24):
            local = first + timedelta(hours=i)
            p, w = cell(cells, local.date(), local.hour)
            utc = local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
            hours.append(
                {
                    "start_utc": utc.isoformat(),
                    "hour_local": local.hour,
                    "dow": local.weekday(),
                    "p_home": round(p, 4),
                }
            )
            weights.append(w)
        terms = self._terms(profile, sum(weights) / len(weights))
        return Inference(
            kind="prediction",
            subject_type="user",
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=datetime.fromisoformat(hours[0]["start_utc"]),
            window_end=datetime.fromisoformat(hours[-1]["start_utc"]) + timedelta(hours=1),
            context={"horizon_hours": 24, "tz": tz},
            expected={"hours": hours},
            probability=hours[0]["p_home"],
            confidence=round(terms.value, 4),
            n_eff=round(sum(weights) / len(weights), 3),
            evidence={"terms": terms.as_dict(), "username": profile.params.get("username")},
            expires_at=now_utc + timedelta(hours=26),
        )


def cells_from_params(params):
    """The inverse of the serialisation in fit_user()."""
    return {
        "m0": params["m0"],
        "p_dow": params["p_dow"],
        "w_dow": params["w_dow"],
        "p_dt": params["p_daytype"],
        "w_dt": params["w_daytype"],
    }


def run_fit(lake_dir, conn, now_utc=None, tz=None):
    """The nightly job: fit every person from the gold layer, store the profiles, drop stale ones,
    and replace the rolling 24 h outlook. Returns counts."""
    learner = PresenceLearner()
    profiles = learner.fit(lake_dir)
    if not profiles:
        return {"profiles": 0, "removed": 0, "predictions": 0}
    now_utc = now_utc or utcnow()
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    predictions = [learner.predict(p, now_utc, tz or silver.TIMEZONE) for p in profiles]
    inference_store.replace_predictions(conn, NAME, predictions)
    return {"profiles": len(profiles), "removed": removed, "predictions": len(predictions)}


# --- Reading the lake ----------------------------------------------------------------------


def load_gold(lake_dir):
    """({user_id: [(date, hour, dow, minutes, observed)]}, {user_id: [(start, end, sightings)]},
    {user_id: (username, user_type)}) from the gold grid and the silver presence intervals."""
    grid_path = os.path.join(lake_dir, "gold", "presence_grid", "part-0.parquet")
    intervals_path = os.path.join(lake_dir, "silver", "presence_intervals", "part-0.parquet")
    if not (os.path.exists(grid_path) and os.path.exists(intervals_path)):
        return {}, {}, {}
    con = duckdb.connect()
    try:
        grid, intervals, users = {}, {}, {}
        for uid, name, d, h, dow, minutes, ok in con.execute(
            f"SELECT user_id, username, date_local, hour_local, dow_local, minutes_home, observed "
            f"FROM read_parquet('{grid_path}') ORDER BY user_id, bucket_utc"
        ).fetchall():
            grid.setdefault(uid, []).append((d, h, dow, minutes, ok))
            users.setdefault(uid, (name, None))
        for uid, utype, start, end, n in con.execute(
            f"SELECT user_id, user_type, start_utc, end_utc, sightings "
            f"FROM read_parquet('{intervals_path}')"
        ).fetchall():
            intervals.setdefault(uid, []).append((start, end, n))
            users[uid] = (users.get(uid, (None, None))[0], utype)
        return grid, intervals, users
    finally:
        con.close()


# --- Replay and backtest (walk-forward, no leakage) ----------------------------------------


def observed_state(intervals, at_utc):
    """(home, away_minutes) at a past instant, as the live user.state would have read: a person is
    home until LIVE_OFFLINE_LAG_MINUTES after their last sighting."""
    last_end = None
    for start, end, _n in intervals:
        if start <= at_utc:
            last_end = end
        else:
            break
    if last_end is None:
        return False, None
    minutes_since = (at_utc - last_end).total_seconds() / 60.0
    if minutes_since <= LIVE_OFFLINE_LAG_MINUTES:
        return True, None
    return False, minutes_since


def replay(lake_dir, user_id, at_local, tz=None, learner=None):
    """What would the model have said about `user_id` at `at_local` (naive local datetime), having
    seen only data before that day? Returns a dict with the profile terms and the Inference (or
    None)."""
    learner = learner or PresenceLearner()
    tz = tz or silver.TIMEZONE
    grid, intervals, users = load_gold(lake_dir)
    if user_id not in grid:
        raise ValueError(f"no presence data for user {user_id}")
    ref = at_local.date() - timedelta(days=1)
    profile = learner.fit_user(
        user_id,
        users[user_id][0],
        [r for r in grid[user_id] if r[0] <= ref],
        intervals[user_id],
        ref,
    )
    if profile is None:
        return {"profile": None, "inference": None}
    zone = ZoneInfo(tz)
    at_utc = at_local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    ivs = sorted(intervals[user_id])
    home, away = observed_state(ivs, at_utc)
    inference = learner.score(
        profile, {"home": home, "away_minutes": away, "local_dt": at_local}, at_utc
    )
    p_home, weight = cell(cells_from_params(profile.params), at_local.date(), at_local.hour)
    return {
        "profile": {
            "coverage": profile.coverage,
            "source_quality": profile.source_quality,
            "stability": profile.stability,
            "stability_detail": profile.params["stability_detail"],
            "fitted_to": profile.fitted_to,
        },
        "cell": {"p_home": p_home, "weight": weight},
        "observed": {"home": home, "away_minutes": away},
        "inference": inference,
    }


def backtest(lake_dir, user_id, start, end, tz=None, learner=None, hours=range(24)):
    """Evaluate the model at hh:30 of every observed hour in [start, end], each day with a model
    fitted only on earlier days. Returns one dict per evaluated hour."""
    learner = learner or PresenceLearner()
    tz = tz or silver.TIMEZONE
    zone = ZoneInfo(tz)
    grid, intervals, users = load_gold(lake_dir)
    rows = grid.get(user_id, [])
    ivs = sorted(intervals.get(user_id, []))
    observed_hours = {(d, h) for d, h, _dw, _m, ok in rows if ok}
    results = []
    day = start
    while day <= end:
        ref = day - timedelta(days=1)
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            [r for r in rows if r[0] <= ref],
            intervals.get(user_id, []),
            ref,
        )
        if profile is not None:
            for hour in hours:
                if (day, hour) not in observed_hours:
                    continue
                at_local = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=30)
                at_utc = at_local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
                home, away = observed_state(ivs, at_utc)
                inf = learner.score(
                    profile, {"home": home, "away_minutes": away, "local_dt": at_local}, at_utc
                )
                p_home, weight = cell(cells_from_params(profile.params), day, hour)
                results.append(
                    {
                        "at_local": at_local,
                        "home": home,
                        "away_minutes": away,
                        "p_home": p_home,
                        "weight": weight,
                        "inference": inf,
                        "profile": profile,
                    }
                )
        day += timedelta(days=1)
    return results


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    lake = os.environ.get("SA_LAKE_DIR", "/lake")
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command == "replay":
        uid, when = int(sys.argv[2]), datetime.fromisoformat(sys.argv[3])
        out = replay(lake, uid, when)
        print(out["profile"], out.get("cell"), out.get("observed"), sep="\n")
        inf = out["inference"]
        print(
            "inference:", None if inf is None else (inf.probability, inf.surprise, inf.confidence)
        )
    else:
        print("usage: python -m sa.learners.presence replay <user_id> <local ISO datetime>")
