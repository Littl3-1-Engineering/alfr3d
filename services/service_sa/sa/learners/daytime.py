"""Daytime-at-home learner: is this person home unusually much today (LF-6 `day_off`'s input,
todo/sa/todo_lf6_layer2.md).

`day_off` used to read the presence learner's hourly p(home). That is the wrong unit for "a day
they are usually out": the hourly cell of a part-time resident is small at EVERY hour (their phone
is seen rarely), so any hour at home looks improbable, while a day at home is routine for them
(Vanja is home 4+ hours of 09:00-17:00 on about one day in five). This learner asks the day-level
question instead.

Model
-----
For each past day the person was observed through the daytime window (WINDOW_START_HOUR to
WINDOW_END_HOUR, local), it keeps the cumulative hours at home by each checkpoint hour
(MIN_EVAL_HOUR..WINDOW_END_HOUR). Scoring at local hour h, with x the hours at home between 09:00
and min(h, 17):00 so far, the probability is the survival

    p = (S + 0.5) / (W + 1)    S = sum of weights of comparable days with cumulative hours >= x
                               W = sum of weights of comparable days

where comparable means the same kind of day (weekday vs. weekend or Ontario holiday), weighted by
recency with a DAYTIME_HALF_LIFE_DAYS half-life. Only unusual MORE time at home is scored (x > 0),
which is the `day_off` question; the calendar corroborates in layer 2.

Confidence is sa/confidence.py's product: sufficiency of the comparable weight, the collector's
coverage, the phone's source quality and a stability term (see stability_of; it can be passed in, e.g. by tests).
"""

import math
from datetime import datetime, timedelta

from sa import confidence
from sa.learners import presence
from sa.learners.base import Inference, Learner, Profile

NAME = "daytime_profile"
VERSION = "1"
SIGNAL = "presence.daytime"

WINDOW_START_HOUR = 9
WINDOW_END_HOUR = 17
MIN_EVAL_HOUR = 12  # three hours of the window have passed
HALF_LIFE_DAYS = 42.0
HISTORY_DAYS = 180
MIN_DAYS = 14
MIN_COMPARABLE_WEIGHT = 8.0
MIN_SURPRISE_BITS = 3.0
STABILITY_UNKNOWN = 0.5
STABILITY_WINDOW_DAYS = 14
STABILITY_SCALE_BITS = 1.0  # a bit more typical surprise in the recent window than before: 0
MIN_STABILITY_DAYS = 5  # days needed in each window to measure it
MAX_STABILITY_BITS = 6.0  # one freak day must not set the window's error
CHECKPOINTS = tuple(range(MIN_EVAL_HOUR, WINDOW_END_HOUR + 1))


def eval_hour(local_hour):
    """The checkpoint a local hour of day maps to, or None before the first one."""
    if local_hour < MIN_EVAL_HOUR:
        return None
    return min(local_hour, WINDOW_END_HOUR)


def days_from_rows(rows, ref):
    """[(offday, weight, [cumulative hours at each checkpoint])] for days up to `ref` that were
    observed through the whole window. rows: (date, hour, dow, minutes_home, observed)."""
    by_day = {}
    for day, hour, _dow, minutes, ok in rows:
        if ok and day <= ref and WINDOW_START_HOUR <= hour < WINDOW_END_HOUR:
            by_day.setdefault(day, {})[hour] = minutes
    width = WINDOW_END_HOUR - WINDOW_START_HOUR
    days = []
    for day, hours in sorted(by_day.items()):
        age = (ref - day).days
        if len(hours) < width or age > HISTORY_DAYS:
            continue
        cumulative, running = [], 0.0
        for checkpoint in CHECKPOINTS:
            running = sum(hours[h] for h in range(WINDOW_START_HOUR, checkpoint)) / 60.0
            cumulative.append(round(running, 3))
        days.append((presence.is_offday(day), 0.5 ** (age / HALF_LIFE_DAYS), cumulative))
    return days


def survival(days, offday, checkpoint, hours_home):
    """(p, comparable weight): the smoothed share of comparable past days with at least
    `hours_home` hours at home by the checkpoint."""
    index = CHECKPOINTS.index(checkpoint)
    total = lasted = 0.0
    for day_offday, weight, cumulative in days:
        if day_offday != offday:
            continue
        total += weight
        if cumulative[index] >= hours_home - 1e-9:
            lasted += weight
    return (lasted + 0.5) / (total + 1.0), total


def stability_of(rows, ref):
    """How well the daytime totals of the last STABILITY_WINDOW_DAYS were predicted by a model
    fitted only on days before them, against the window before that: each day's surprise at the
    last checkpoint (-log2 of the smoothed share of comparable earlier days at least as long at
    home), the window's error the median, stability falling from 1 as the recent error exceeds
    the earlier one by STABILITY_SCALE_BITS. STABILITY_UNKNOWN with too few days in a window."""
    observed = list(_observed_days(rows))

    def window_error(lo, hi):
        model = days_from_rows([r for r in rows if r[0] <= lo], lo)
        errors = []
        for day in observed:
            if lo < day["date"] <= hi:
                p, weight = survival(
                    model, presence.is_offday(day["date"]), CHECKPOINTS[-1], day["cumulative"][-1]
                )
                if weight >= MIN_COMPARABLE_WEIGHT:
                    errors.append(min(-math.log2(p), MAX_STABILITY_BITS))
        if len(errors) < MIN_STABILITY_DAYS:
            return None
        errors.sort()
        mid = len(errors) // 2
        return errors[mid] if len(errors) % 2 else (errors[mid - 1] + errors[mid]) / 2.0

    w = timedelta(days=STABILITY_WINDOW_DAYS)
    recent, prior = window_error(ref - w, ref), window_error(ref - 2 * w, ref - w)
    if recent is None or prior is None:
        return STABILITY_UNKNOWN
    return max(0.0, 1.0 - max(0.0, recent - prior) / STABILITY_SCALE_BITS)


class DaytimeLearner(Learner):
    name = NAME
    version = VERSION

    def fit_user(self, user_id, username, rows, ref, coverage, source_quality, stability=None):
        """Profile for one person, or None with too few observed days. rows: the gold hourly
        presence grid, (date, hour, dow, minutes_home, observed)."""
        days = days_from_rows(rows, ref)
        if len(days) < MIN_DAYS:
            return None
        return Profile(
            learner=self.name,
            learner_version=self.version,
            subject_type="user",
            subject_id=user_id,
            signal=SIGNAL,
            params={
                "days": [[int(o), round(w, 4), c] for o, w, c in days],
                "username": username,
                "half_life_days": HALF_LIFE_DAYS,
            },
            n_eff=round(sum(d[1] for d in days), 3),
            coverage=coverage,
            source_quality=source_quality,
            stability=round(stability_of(rows, ref) if stability is None else stability, 4),
            fitted_from=None,
            fitted_to=ref,
        )

    def score(self, profile, state, now):
        """A deviation Inference if the person has been home improbably long today, else None.
        state: {"hours_home": float (09:00 to the checkpoint), "local_dt": naive local datetime,
        "day_start": naive UTC local midnight}. `now`: naive UTC."""
        checkpoint = eval_hour(state["local_dt"].hour)
        hours_home = state["hours_home"]
        if checkpoint is None or hours_home <= 0:
            return None
        day = state["local_dt"].date()
        offday = presence.is_offday(day)
        days = [(bool(o), w, c) for o, w, c in profile.params["days"]]
        p, weight = survival(days, offday, checkpoint, hours_home)
        if weight < MIN_COMPARABLE_WEIGHT:
            return None
        surprise = -math.log2(p)
        if surprise < MIN_SURPRISE_BITS:
            return None
        terms = confidence.Confidence(
            confidence.sufficiency(weight),
            profile.coverage,
            profile.source_quality,
            profile.stability,
        )
        return Inference(
            kind="deviation",
            subject_type="user",
            subject_id=profile.subject_id,
            signal=SIGNAL,
            learner=self.name,
            learner_version=self.version,
            window_start=state["day_start"].replace(microsecond=0),
            window_end=now.replace(microsecond=0),
            context={
                "daytype": presence._daytype(day),
                "window": f"{WINDOW_START_HOUR:02d}:00-{checkpoint:02d}:00",
            },
            observed={"state": "home", "hours_home": round(hours_home, 2)},
            expected={"p_at_least": round(p, 4)},
            probability=round(p, 6),
            surprise=round(surprise, 3),
            confidence=round(terms.value, 4),
            n_eff=round(weight, 3),
            evidence={"terms": terms.as_dict(), "username": profile.params.get("username")},
            expires_at=now + timedelta(hours=6),
        )


def run_fit(lake_dir, conn):
    """The nightly job: fit every person from the gold grid and store the profiles."""
    from sa import inference_store

    grid, intervals, users = presence.load_gold(lake_dir)
    if not grid:
        return {"profiles": 0, "removed": 0}
    ref = max(r[0] for rows in grid.values() for r in rows)
    learner = DaytimeLearner()
    profiles = []
    for user_id, rows in sorted(grid.items()):
        person = intervals.get(user_id, [])
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            rows,
            ref,
            presence.coverage_of(rows, ref),
            presence.source_quality_of(person, ref),
        )
        if profile is not None:
            profiles.append(profile)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    return {"profiles": len(profiles), "removed": removed}


def backtest(lake_dir, user_id, start, end, checkpoints=(13, 17)):
    """Walk-forward: for each day in [start, end] and checkpoint, a profile fitted on earlier days
    only, scored on that day's cumulative hours at home. One dict per scored (day, checkpoint)."""
    grid, intervals, users = presence.load_gold(lake_dir)
    rows = grid.get(user_id, [])
    person = intervals.get(user_id, [])
    learner = DaytimeLearner()
    actual = {d["date"]: d["cumulative"] for d in _observed_days(rows)}
    out = []
    day = start
    while day <= end:
        ref = day - timedelta(days=1)
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            [r for r in rows if r[0] <= ref],
            ref,
            presence.coverage_of([r for r in rows if r[0] <= ref], ref),
            presence.source_quality_of(person, ref),
        )
        if profile is not None and day in actual:
            for checkpoint in checkpoints:
                x = actual[day][CHECKPOINTS.index(checkpoint)]
                at = datetime.combine(day, datetime.min.time()).replace(hour=checkpoint)
                inference = learner.score(
                    profile,
                    {"hours_home": x, "local_dt": at, "day_start": at.replace(hour=0)},
                    at,
                )
                out.append(
                    {"date": day, "checkpoint": checkpoint, "hours_home": x, "inference": inference}
                )
        day += timedelta(days=1)
    return out


def _observed_days(rows):
    by_day = {}
    for day, hour, _dow, minutes, ok in rows:
        if ok and WINDOW_START_HOUR <= hour < WINDOW_END_HOUR:
            by_day.setdefault(day, {})[hour] = minutes
    width = WINDOW_END_HOUR - WINDOW_START_HOUR
    for day, hours in sorted(by_day.items()):
        if len(hours) == width:
            yield {
                "date": day,
                "cumulative": [
                    sum(hours[h] for h in range(WINDOW_START_HOUR, c)) / 60.0 for c in CHECKPOINTS
                ],
            }
