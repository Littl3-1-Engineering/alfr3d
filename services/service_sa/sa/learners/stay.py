"""Stay-length learner: how long does this person usually stay, and is today's stay unusually long
(todo/sa/todo_lf4b_baseline_ports.md, the `departure_anomaly` port).

The presence learner (presence.py) answers "how likely is this person to be home at this hour".
That is the wrong question for "still home, usually gone by now": a part-time resident is rarely
home at ANY hour, so being home is always improbable and every visit scores as an anomaly. What
`departure_anomaly` means is an overstay, a duration question, so this learner models stay length.

Model
-----
A stay is one merged presence interval (silver, phone sightings with gaps under
PRESENCE_GAP_MINUTES): an arrival, then a departure. Stays shorter than MIN_STAY_MINUTES are
blips and neither teach the model nor get scored. For a stay in progress, the question is the
survival probability

    p = P(a comparable past stay lasted at least this long)

"Comparable" is a soft match, a weight per past stay: a Gaussian on the circular distance between
arrival times of day (sigma ARRIVAL_SIGMA_HOURS, so an overnight stay compares with overnight
stays and a lunchtime visit with lunchtime visits), times DAYTYPE_MISMATCH_WEIGHT when the stay
ended on the other kind of day (weekday vs. weekend or holiday), times a recency weight with a
STAY_HALF_LIFE_DAYS half-life. The probability is Laplace-smoothed, (S + 0.5) / (W + 1), so a thin
history cannot claim certainty; surprise = -log2 p. A person whose stays are long and scattered
has a fat tail and nothing is ever surprising; a person who is always gone within the hour is
surprised by the second.

Confidence is sa/confidence.py's product: sufficiency of the comparable weight, the collector's
coverage, the phone's source quality and a stability term. Stability is not measured here yet and
is passed in (default STABILITY_UNKNOWN), so read confidence as an upper bound.
"""

import math
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from sa import confidence, silver
from sa.learners import presence
from sa.learners.base import Inference, Learner, Profile

NAME = "stay_profile"
VERSION = "1"
SIGNAL = "presence.stay"

MIN_STAY_MINUTES = 60
STAY_HALF_LIFE_DAYS = 42.0
HISTORY_DAYS = 180  # older stays carry < 5 % weight and only bloat the stored profile
LOOKBACK_DAYS = 4  # how far back the live stay start is searched; a longer stay reads as this long
ARRIVAL_SIGMA_HOURS = 2.5
DAYTYPE_MISMATCH_WEIGHT = 0.25
MIN_COMPARABLE_WEIGHT = 5.0
MIN_SURPRISE_BITS = 3.0
STABILITY_UNKNOWN = 0.5
LIVE_OFFLINE_LAG_MINUTES = presence.LIVE_OFFLINE_LAG_MINUTES
# Who can overstay: the legacy rule's audience. A guest staying several days is just a guest.
OVERSTAY_USER_TYPES = ("owner", "technoking", "resident")


def _local(utc, zone):
    return utc.replace(tzinfo=timezone.utc).astimezone(zone)


def stays_from_intervals(intervals, ref, zone):
    """[(arrival_hour_local, ends_offday, minutes, weight)] for the stays that ended by the end of
    `ref` (a date). intervals: (start_utc, end_utc, sightings)."""
    stays = []
    for start, end, _n in intervals:
        minutes = (end - start).total_seconds() / 60.0 + 1.0
        if minutes < MIN_STAY_MINUTES:
            continue
        end_local = _local(end, zone)
        age = (ref - end_local.date()).days
        if age < 0 or age > HISTORY_DAYS:
            continue
        start_local = _local(start, zone)
        stays.append(
            (
                start_local.hour + start_local.minute / 60.0,
                presence.is_offday(end_local.date()),
                minutes,
                0.5 ** (age / STAY_HALF_LIFE_DAYS),
            )
        )
    return stays


def _arrival_gap(a, b):
    d = abs(a - b) % 24.0
    return min(d, 24.0 - d)


def survival(stays, arrival_hour, offday, minutes):
    """(p, comparable weight): the smoothed share of comparable past stays that lasted at least
    `minutes`."""
    total = lasted = 0.0
    for s_arrival, s_offday, s_minutes, s_weight in stays:
        gap = _arrival_gap(s_arrival, arrival_hour)
        w = s_weight * math.exp(-0.5 * (gap / ARRIVAL_SIGMA_HOURS) ** 2)
        if s_offday != offday:
            w *= DAYTYPE_MISMATCH_WEIGHT
        total += w
        if s_minutes >= minutes:
            lasted += w
    return (lasted + 0.5) / (total + 1.0), total


class StayLearner(Learner):
    name = NAME
    version = VERSION

    def fit_user(
        self, user_id, username, intervals, ref, coverage, source_quality, stability=None, tz=None
    ):
        """Profile for one person, or None with too few stays to compare against.
        intervals: (start_utc, end_utc, sightings); ref: the last date of history to use."""
        zone = ZoneInfo(tz or silver.TIMEZONE)
        stays = stays_from_intervals(intervals, ref, zone)
        weight = sum(s[3] for s in stays)
        if weight < MIN_COMPARABLE_WEIGHT:
            return None
        return Profile(
            learner=self.name,
            learner_version=self.version,
            subject_type="user",
            subject_id=user_id,
            signal=SIGNAL,
            params={
                "stays": [[round(a, 2), int(o), round(m, 1), round(w, 4)] for a, o, m, w in stays],
                "username": username,
                "half_life_days": STAY_HALF_LIFE_DAYS,
            },
            n_eff=round(weight, 3),
            coverage=coverage,
            source_quality=source_quality,
            stability=STABILITY_UNKNOWN if stability is None else stability,
            fitted_from=None,
            fitted_to=ref,
        )

    def score(self, profile, state, now, tz=None):
        """A deviation Inference if the stay so far is improbably long, else None.
        state: {"stay_start": naive UTC datetime of this stay's arrival}. `now`: naive UTC."""
        zone = ZoneInfo(tz or silver.TIMEZONE)
        minutes = (now - state["stay_start"]).total_seconds() / 60.0
        if minutes < MIN_STAY_MINUTES:
            return None
        arrival = _local(state["stay_start"], zone)
        arrival_hour = arrival.hour + arrival.minute / 60.0
        today = _local(now, zone).date()
        stays = [(a, bool(o), m, w) for a, o, m, w in profile.params["stays"]]
        p, weight = survival(stays, arrival_hour, presence.is_offday(today), minutes)
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
            window_start=state["stay_start"].replace(microsecond=0),
            window_end=now.replace(microsecond=0),
            context={"daytype": presence._daytype(today), "arrival_hour": round(arrival_hour, 1)},
            observed={"state": "home", "stay_minutes": round(minutes, 1)},
            expected={"p_stay_at_least": round(p, 4)},
            probability=round(p, 6),
            surprise=round(surprise, 3),
            confidence=round(terms.value, 4),
            n_eff=round(weight, 3),
            evidence={"terms": terms.as_dict(), "username": profile.params.get("username")},
            expires_at=now + timedelta(hours=6),
        )


def current_stay_start(intervals, at_utc):
    """Start (naive UTC) of the stay in progress at `at_utc`, or None if the person is away: a
    person is home until LIVE_OFFLINE_LAG_MINUTES after their last sighting, like user.state."""
    last = None
    for start, end, _n in intervals:
        if start > at_utc:
            break
        last = (start, end)
    if last is None:
        return None
    start, end = last
    if (at_utc - min(end, at_utc)).total_seconds() / 60.0 > LIVE_OFFLINE_LAG_MINUTES:
        return None
    return start


def stay_start_from_sightings(sightings, gap_minutes=silver.PRESENCE_GAP_MINUTES):
    """Start (naive UTC) of the stay that ends at the newest sighting: walk back while consecutive
    sightings are at most `gap_minutes` apart, the rule silver merges presence intervals by. Returns
    None with no sightings."""
    times = sorted(sightings)
    if not times:
        return None
    start = times[-1]
    for earlier in reversed(times[:-1]):
        if (start - earlier).total_seconds() / 60.0 > gap_minutes:
            break
        start = earlier
    return start


def run_fit(lake_dir, conn, tz=None):
    """The nightly job: fit every person's stay profile from the lake and store them (the layer-1
    inference contract's sa_profiles), dropping anyone who no longer has enough history."""
    from sa import inference_store

    grid, intervals, users = presence.load_gold(lake_dir)
    if not grid:
        return {"profiles": 0, "removed": 0}
    ref = max(r[0] for rows in grid.values() for r in rows)
    learner = StayLearner()
    profiles = []
    for user_id, rows in sorted(grid.items()):
        person = intervals.get(user_id, [])
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            person,
            ref,
            presence.coverage_of(rows, ref),
            presence.source_quality_of(person, ref),
            tz=tz,
        )
        if profile is not None:
            profiles.append(profile)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    return {"profiles": len(profiles), "removed": removed}


def backtest(lake_dir, user_id, start, end, hours=range(24), tz=None):
    """Walk-forward: at hh:30 of every day in [start, end] for each hour in `hours`, a profile
    fitted only on stays that ended before that day, scored against the stay then in progress.
    One dict per evaluation where the person was home."""
    from datetime import datetime  # local: only the replay needs it

    zone = ZoneInfo(tz or silver.TIMEZONE)
    learner = StayLearner()
    grid, intervals, users = presence.load_gold(lake_dir)
    ivs = sorted(intervals.get(user_id, []))
    rows = grid.get(user_id, [])
    results = []
    day = start
    while day <= end:
        ref = day - timedelta(days=1)
        past = [i for i in ivs if _local(i[1], zone).date() <= ref]
        seen = [r for r in rows if r[0] <= ref]
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            past,
            ref,
            presence.coverage_of(seen, ref),
            presence.source_quality_of(past, ref),
            tz=tz,
        )
        if profile is not None:
            for hour in hours:
                at_local = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=30)
                at_utc = at_local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
                stay_start = current_stay_start(ivs, at_utc)
                if stay_start is None:
                    continue
                inf = learner.score(profile, {"stay_start": stay_start}, at_utc, tz=tz)
                results.append(
                    {
                        "at_local": at_local,
                        "stay_minutes": (at_utc - stay_start).total_seconds() / 60.0,
                        "inference": inf,
                    }
                )
        day += timedelta(days=1)
    return results
