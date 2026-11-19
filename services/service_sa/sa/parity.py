"""Replay-versus-live parity (Timeline "Context learning 1/5", todo/sa/todo_lf7_replay_harness.md).

The replay harness (sa/replay.py) answers "what would today's code say". This module answers the
narrower question that makes a replay trustworthy: **replaying a day from the lake as live saw it,
does it give the answer live gave?** The 2026-10-12 household device-count bug was caught by hand
with this comparison; this makes it repeatable.

How it stays honest:

- Live scores day D with the profile fitted nightly through D-1. Profiles are not versioned and the
  lake only gains day D at the same nightly build that replaces that profile, so the profile live
  used cannot be read back. It is rebuilt instead: a refit from the lake with data through D-1,
  scored on a 15-minute grid of lake state across D. That is the same walk-forward the learners'
  own `backtest` does, at live's cadence rather than hourly.
- That rebuild equals what live used only while the lake's *inputs* are unchanged. A change to a
  learner or to silver (the presence bridge of 2026-11-01 re-cut every earlier stay) makes the
  replay of earlier days hindsight (replay.BRIDGE_HINDSIGHT). So comparison starts at an explicit
  per-learner date (`MATCHING_INPUTS_SINCE`); advance a date after any change to that learner or
  to silver, never backwards.
- The stored profile is also checked directly: refit from the lake as of its `fitted_to` and
  compared (n_eff, coverage, source quality, stability). Stability may legitimately be lower in the
  store (the drift detector caps it after the fit), never higher.

Per (learner, subject, day) the outcome is `both`, `live_only`, `replay_only` or `neither`, plus the
score pairs on days both flagged. `live_only` and `replay_only` days are mismatches to explain; so
is a day both flagged where only one reached the card confidence floor. Score pairs are
approximate: a stored row holds its LAST refresh (a multi-day stay is one row refreshed until it
ends; a day's daytime row holds the last checkpoint), while the replay keeps the day's strongest.

The verdict pools subject-days per learner (one person-day is one sample): INSUFFICIENT below
`MIN_SUBJECT_DAYS`, so a single quiet day can never read as a pass.

Read-only: lake and database reads, no writes. Covered: presence, stay, daytime, household_day,
scalar, rates and device_rhythm (the last approximate: the lake has sessions, not the `device`
row's live state). Not yet: drift.
"""

import bisect
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sa import replay, silver
from sa.learners import (
    daytime,
    device_rhythm,
    household_day,
    presence,
    rates,
    scalar,
    stay,
)

# The first day each learner's live inputs match what the lake rebuilds today. Advance a date after
# any later change to that learner or to silver; never move one backwards.
#   2026-11-02: the learned presence bridge (PR #365) was deployed during 2026-11-01, so that day's
#               live profile was fitted before it (found by this check: user 6, live 3.12 bits
#               against 2.99 replayed).
#   2026-11-19: the stay-arrival fix (`shadow._stay_start`), deployed the evening of 2026-11-18.
#   2026-11-15: device-rhythm availability flags began using the stability of the day type they
#               fire on (2026-11-14); event-rate `play_start` profiles halved at the next refit
#               after the now-playing de-duplication (2026-11-15), so rates start 2026-11-16.
MATCHING_INPUTS_SINCE = {
    presence.NAME: date(2026, 11, 2),
    daytime.NAME: date(2026, 11, 2),
    household_day.NAME: date(2026, 11, 2),
    stay.NAME: date(2026, 11, 19),
    scalar.NAME: date(2026, 11, 2),
    rates.NAME: date(2026, 11, 16),
    device_rhythm.NAME: date(2026, 11, 15),
}
# A one-sided day whose flagged score is within this many bits of the learner's bar is borderline,
# not a mismatch: the nightly silver rebuild re-derives history with the bridge learned that night,
# so the same day scores a little differently live than from today's lake. Reported, never hidden.
NEAR_BAR_BITS = 0.5
# A z-based learner's bar sits near 14 bits, where half a sigma is about 3 bits: its band is the
# bits between MIN_ABS_Z and MIN_ABS_Z + 0.5 sigma, not a fixed 0.5 bits.
NEAR_BAR_Z = 0.5


def _z_bits(z):
    """Surprise in bits of a two-sided tail at `z` sigma."""
    return -math.log2(scalar.two_sided_p(z))


BAR_BITS = {
    presence.NAME: presence.MIN_SURPRISE_BITS,
    stay.NAME: stay.MIN_SURPRISE_BITS,
    daytime.NAME: daytime.MIN_SURPRISE_BITS,
    scalar.NAME: _z_bits(scalar.MIN_ABS_Z),
    rates.NAME: -math.log2(rates.P_FLAG),
    device_rhythm.NAME: device_rhythm.MIN_SURPRISE_BITS,
}
NEAR_BAR_MARGIN_BITS = {
    scalar.NAME: _z_bits(scalar.MIN_ABS_Z + NEAR_BAR_Z) - _z_bits(scalar.MIN_ABS_Z),
}
MIN_SUBJECT_DAYS = 14
GRID_MINUTES = 15
PROFILE_TOLERANCE = 1e-3
MIN_OBSERVED_HOURS = 20  # a day counts as observed with this many observed grid hours


def _zone(tz=None):
    return ZoneInfo(tz or silver.TIMEZONE)


def local_day(ts, zone):
    """The local calendar day of a naive-UTC stamp. Window starts are stamped a second before local
    midnight (microsecond truncation), so one second is added before converting."""
    shifted = ts + timedelta(seconds=1)
    return shifted.replace(tzinfo=timezone.utc).astimezone(zone).date()


def window(since, last_data_day, today):
    """(first, last) comparable local days, or None. Today is never complete."""
    last = min(last_data_day, today - timedelta(days=1))
    return (since, last) if last >= since else None


def _span(first, last):
    out, day = [], first
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def _grid(day, zone):
    """(naive local, naive UTC) for every GRID_MINUTES of a local day."""
    base = datetime.combine(day, datetime.min.time())
    for step in range(0, 24 * 60, GRID_MINUTES):
        at_local = base + timedelta(minutes=step)
        at_utc = at_local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        yield at_local, at_utc


def _fold(per_day, day, inference):
    """Keep the strongest inference of a day: {"bits", "confidence", "n"}."""
    if inference is None:
        return
    row = per_day.setdefault(day, {"bits": 0.0, "confidence": 0.0, "n": 0})
    row["n"] += 1
    row["bits"] = max(row["bits"], inference.surprise or 0.0)
    row["confidence"] = max(row["confidence"], inference.confidence or 0.0)


# --- Walk-forward replays at live's cadence ---------------------------------------------------


def walk_presence(lake_dir, user_id, first, last, tz=None):
    """{day: strongest presence deviation}: each day scored with a profile refitted through the
    day before, on a 15-minute grid."""
    zone = _zone(tz)
    learner = presence.PresenceLearner()
    grid, intervals, users = presence.load_gold(lake_dir)
    rows = grid.get(user_id, [])
    ivs = sorted(intervals.get(user_id, []))
    observed = {(d, h) for d, h, _dw, _m, ok in rows if ok}
    per_day = {}
    for day in _span(first, last):
        ref = day - timedelta(days=1)
        profile = learner.fit_user(
            user_id, users[user_id][0], [r for r in rows if r[0] <= ref], ivs, ref
        )
        if profile is None:
            continue
        for at_local, at_utc in _grid(day, zone):
            if (day, at_local.hour) not in observed:
                continue
            home, away = presence.observed_state(ivs, at_utc)
            state = {"home": home, "away_minutes": away, "local_dt": at_local}
            _fold(per_day, day, learner.score(profile, state, at_utc))
    return per_day


def walk_stay(lake_dir, user_id, first, last, tz=None):
    zone = _zone(tz)
    learner = stay.StayLearner()
    grid, intervals, users = presence.load_gold(lake_dir)
    rows = grid.get(user_id, [])
    ivs = sorted(intervals.get(user_id, []))
    per_day = {}
    for day in _span(first, last):
        ref = day - timedelta(days=1)
        past = [i for i in ivs if stay._local(i[1], zone).date() <= ref]
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
        if profile is None:
            continue
        for _at_local, at_utc in _grid(day, zone):
            start = stay.current_stay_start(ivs, at_utc)
            if start is not None:
                _fold(per_day, day, learner.score(profile, {"stay_start": start}, at_utc, tz=tz))
    return per_day


def walk_daytime(lake_dir, user_id, first, last, tz=None):
    learner = daytime.DaytimeLearner()
    grid, intervals, users = presence.load_gold(lake_dir)
    rows = grid.get(user_id, [])
    actual = {d["date"]: d["cumulative"] for d in daytime._observed_days(rows)}
    per_day = {}
    for day in _span(first, last):
        if day not in actual:
            continue
        ref = day - timedelta(days=1)
        seen = [r for r in rows if r[0] <= ref]
        profile = learner.fit_user(
            user_id,
            users[user_id][0],
            seen,
            ref,
            presence.coverage_of(seen, ref),
            presence.source_quality_of(intervals.get(user_id, []), ref),
        )
        if profile is None:
            continue
        for checkpoint in daytime.CHECKPOINTS:
            at = datetime.combine(day, datetime.min.time()).replace(hour=checkpoint)
            state = {
                "hours_home": actual[day][daytime.CHECKPOINTS.index(checkpoint)],
                "local_dt": at,
                "day_start": at.replace(hour=0),
            }
            _fold(per_day, day, learner.score(profile, state, at))
    return per_day


def walk_household(lake_dir, _subject, first, last, tz=None):
    """{day: ...} for days the household rule's own calibrated bar was cleared (no confidence: the
    bar, not a confidence floor, gates this rule)."""
    per_day = {}
    for hit in household_day.backtest(lake_dir, first, last):
        if hit["flagged"]:
            per_day[hit["date"]] = {"bits": hit["bits"], "confidence": None, "n": 1}
    return per_day


def walk_scalar(lake_dir, series_key, first, last, tz=None):
    """{day: strongest deviation} for one numeric series: each day scored with a profile fitted on
    the days before it, every observed hour."""
    learner = scalar.ScalarLearner()
    grouped, _flags, _ref = scalar.load_series(lake_dir)
    points = grouped.get(series_key, [])
    covariate = (
        grouped.get(scalar.COVARIATE_SERIES) if series_key != scalar.COVARIATE_SERIES else None
    )
    by_time = {p["t"]: p for p in points}
    per_day = {}
    for day in _span(first, last):
        ref = day - timedelta(days=1)
        profile = scalar.fit_points(
            series_key, [p for p in points if p["date"] <= ref], ref, covariate
        )
        if profile is None:
            continue
        for p in points:
            if p["date"] != day or p["coverage"] < scalar.MIN_COVERAGE:
                continue
            state = {
                "value": p["value"],
                "recent": scalar._recent_for(None, by_time, p["t"]),
                "local_dt": datetime.combine(day, datetime.min.time()).replace(hour=p["hour"]),
                "window_start": p["t"],
            }
            _fold(per_day, day, learner.score(profile, state, p["t"] + timedelta(hours=1)))
    return per_day


def walk_rates(lake_dir, stream_key, first, last, tz=None):
    """{day: strongest deviation} for one event or sender stream, each day scored with a profile
    fitted on the days before it."""
    learner = rates.RateLearner()
    data = rates.load_streams(lake_dir)
    stream = data["streams"].get(stream_key)
    per_day = {}
    if not stream:
        return per_day
    for day in _span(first, last):
        profile = rates.fit_stream(
            stream_key,
            stream["window"],
            [p for p in stream["points"] if p["date"] < day],
            day - timedelta(days=1),
            data["daytypes"],
            data["coverage"],
            stream["quality"],
        )
        if profile is None:
            continue
        for p in (q for q in stream["points"] if q["date"] == day):
            start = p["t"] or datetime.combine(day, datetime.min.time())
            state = {
                "count": p["n"],
                "hour": p["hour"],
                "daytype": data["daytypes"].get(day, "work"),
                "window_start": start,
            }
            _fold(per_day, day, learner.score(profile, state, start))
    return per_day


def walk_device(lake_dir, device_id, first, last, tz=None):
    """{day: strongest availability deviation} for one device. APPROXIMATE: the live rule reads the
    `device` row's state and last_online; the lake only has sessions, so a device is taken as
    online until presence.LIVE_OFFLINE_LAG_MINUTES after a session's last sighting, and the
    offline time is measured from there."""
    zone = _zone(tz)
    learner = device_rhythm.DeviceRhythmLearner()
    data = device_rhythm.load_gold(lake_dir)
    rows = data["rows"].get(device_id, [])
    sessions = data["sessions"].get(device_id, [])
    ends = sorted(s[2] for s in sessions)
    observed = {(d, h) for d, h, _dw, _m, ok in rows if ok}
    per_day = {}
    for day in _span(first, last):
        profile = learner.fit_device(
            device_id,
            data["names"].get(device_id),
            [r for r in rows if r[0] < day],
            [s for s in sessions if s[0] < day],
            day - timedelta(days=1),
            data["horizon"],
        )
        if profile is None:
            continue
        for at_local, at_utc in _grid(day, zone):
            if (day, at_local.hour) not in observed:
                continue
            i = bisect.bisect_right(ends, at_utc)
            if i == 0:
                continue
            idle = (at_utc - ends[i - 1]).total_seconds() / 60.0
            online = idle <= presence.LIVE_OFFLINE_LAG_MINUTES
            state = {
                "online": online,
                "offline_minutes": None if online else idle,
                "local_dt": at_local,
            }
            _fold(per_day, day, learner.score(profile, state, at_utc))
    return per_day


def observed_days(lake_dir, user_id, first, last):
    """Days in range on which this person has a (nearly) complete observed day in the gold grid, so
    a 'neither' day means 'checked and quiet', not 'no data'."""
    grid, _i, _u = presence.load_gold(lake_dir)
    seen = {}
    for d, _h, _dw, _m, ok in grid.get(user_id, []):
        if first <= d <= last and ok:
            seen[d] = seen.get(d, 0) + 1
    return [d for d in _span(first, last) if seen.get(d, 0) >= MIN_OBSERVED_HOURS]


def observed_days_scalar(lake_dir, series_key, first, last):
    grouped, _flags, _ref = scalar.load_series(lake_dir)
    seen = {}
    for p in grouped.get(series_key, []):
        if first <= p["date"] <= last and p["coverage"] >= scalar.MIN_COVERAGE:
            seen[p["date"]] = seen.get(p["date"], 0) + 1
    return [d for d in _span(first, last) if seen.get(d, 0) >= MIN_OBSERVED_HOURS // 2]


def observed_days_rates(lake_dir, stream_key, first, last):
    stream = rates.load_streams(lake_dir)["streams"].get(stream_key)
    have = {p["date"] for p in stream["points"]} if stream else set()
    return [d for d in _span(first, last) if d in have]


def observed_days_device(lake_dir, device_id, first, last):
    rows = device_rhythm.load_gold(lake_dir)["rows"].get(device_id, [])
    seen = {}
    for d, _h, _dw, _m, ok in rows:
        if first <= d <= last and ok:
            seen[d] = seen.get(d, 0) + 1
    return [d for d in _span(first, last) if seen.get(d, 0) >= MIN_OBSERVED_HOURS]


# --- Live rows ---------------------------------------------------------------------------------


def live_days(inferences, first, last, zone, start_day_only=False):
    """{day: strongest stored live inference} over [first, last]. A stay or presence row spans the
    days it lived in (a multi-day stay is one row refreshed until it ends). A day-keyed row
    (daytime, household day) belongs to its start day only: its window_end is just the last
    refresh, which can land minutes after local midnight."""
    per_day = {}
    for inf in inferences:
        if inf.window_start is None:
            continue
        lo = local_day(inf.window_start, zone)
        hi = lo if start_day_only or not inf.window_end else local_day(inf.window_end, zone)
        day = max(lo, first)
        while day <= min(hi, last):
            _fold(per_day, day, inf)
            day += timedelta(days=1)
    return per_day


# --- Comparison --------------------------------------------------------------------------------


def compare_days(live, replayed, days, bar=None, margin=NEAR_BAR_BITS):
    """Classify every comparable day. Returns the parity record for one (learner, subject). With
    `bar` (the learner's surprise bar in bits), a one-sided day whose flagged score is within
    `margin` bits (default NEAR_BAR_BITS) of it is `borderline`: counted separately, not a
    mismatch.
    """
    outcomes = {"both": 0, "live_only": 0, "replay_only": 0, "borderline": 0, "neither": 0}
    mismatches, borderline, pairs, flips = [], [], [], []
    floor = replay.CARD_CONFIDENCE_FLOOR
    for day in days:
        in_live, in_replay = day in live, day in replayed
        if in_live and in_replay:
            kind = "both"
            a, b = live[day], replayed[day]
            pairs.append(
                {
                    "day": day.isoformat(),
                    "bits_live": round(a["bits"], 2),
                    "bits_replay": round(b["bits"], 2),
                    "confidence_live": a["confidence"],
                    "confidence_replay": b["confidence"],
                }
            )
            if a["confidence"] is not None and b["confidence"] is not None:
                if (a["confidence"] >= floor) != (b["confidence"] >= floor):
                    flips.append(day.isoformat())
        elif in_live:
            kind = "live_only"
        elif in_replay:
            kind = "replay_only"
        else:
            kind = "neither"
        if kind in ("live_only", "replay_only"):
            entry = {
                "day": day.isoformat(),
                "kind": kind,
                "live": live.get(day),
                "replay": replayed.get(day),
            }
            flagged = live.get(day) or replayed.get(day)
            if bar is not None and flagged["bits"] < bar + margin:
                kind = "borderline"
                borderline.append(entry)
            else:
                mismatches.append(entry)
        outcomes[kind] += 1
    return {
        "comparable_days": len(days),
        "outcomes": outcomes,
        "borderline": borderline,
        "mismatches": mismatches,
        "card_floor_flips": flips,
        "score_pairs": pairs,
    }


def verdict(records):
    """One verdict for a learner from its per-subject records, pooling subject-days."""
    days = sum(r["comparable_days"] for r in records)
    both = sum(r["outcomes"]["both"] for r in records)
    mismatched = sum(len(r["mismatches"]) + len(r["card_floor_flips"]) for r in records)
    if days < MIN_SUBJECT_DAYS:
        return f"INSUFFICIENT: {days} comparable subject-day(s), need {MIN_SUBJECT_DAYS}"
    if mismatched:
        return f"MISMATCH: {mismatched} day(s) to explain"
    near = sum(r["outcomes"].get("borderline", 0) for r in records)
    suffix = f" ({near} borderline day(s) near the learner's bar)" if near else ""
    if both == 0 and not near:
        return "MATCH (neither side flagged anything: agreement on quiet days only)"
    return "MATCH" + suffix


def profile_parity(stored, refit):
    """Stored profile versus a refit from the lake as of `stored.fitted_to`. n_eff, coverage and
    source quality must agree; stability may only be lower in the store (the drift cap)."""
    out = {}
    for field in ("n_eff", "coverage", "source_quality"):
        a, b = getattr(stored, field), getattr(refit, field)
        ok = a is not None and b is not None and abs(a - b) <= PROFILE_TOLERANCE * max(1.0, abs(b))
        out[field] = {"stored": a, "refit": b, "ok": ok}
    a, b = stored.stability, refit.stability
    out["stability"] = {
        "stored": a,
        "refit": b,
        "ok": a is not None and b is not None and a <= b + PROFILE_TOLERANCE,
        "drift_capped": a is not None and b is not None and a < b - PROFILE_TOLERANCE,
    }
    return out


def _refit_presence(lake_dir, stored, tz=None):
    grid, intervals, users = presence.load_gold(lake_dir)
    uid = int(stored.subject_id)
    rows = [r for r in grid.get(uid, []) if r[0] <= stored.fitted_to]
    return presence.PresenceLearner().fit_user(
        uid, users[uid][0], rows, intervals.get(uid, []), stored.fitted_to
    )


def _refit_stay(lake_dir, stored, tz=None):
    zone = _zone(tz)
    grid, intervals, users = presence.load_gold(lake_dir)
    uid = int(stored.subject_id)
    ivs = [i for i in intervals.get(uid, []) if stay._local(i[1], zone).date() <= stored.fitted_to]
    rows = [r for r in grid.get(uid, []) if r[0] <= stored.fitted_to]
    return stay.StayLearner().fit_user(
        uid,
        users[uid][0],
        ivs,
        stored.fitted_to,
        presence.coverage_of(rows, stored.fitted_to),
        presence.source_quality_of(ivs, stored.fitted_to),
        tz=tz,
    )


def _refit_daytime(lake_dir, stored, tz=None):
    grid, intervals, users = presence.load_gold(lake_dir)
    uid = int(stored.subject_id)
    rows = [r for r in grid.get(uid, []) if r[0] <= stored.fitted_to]
    return daytime.DaytimeLearner().fit_user(
        uid,
        users[uid][0],
        rows,
        stored.fitted_to,
        presence.coverage_of(rows, stored.fitted_to),
        presence.source_quality_of(intervals.get(uid, []), stored.fitted_to),
    )


def _int_subject(profile):
    return int(profile.subject_id)


def _str_subject(profile):
    return str(profile.subject_id)


def _household_subject(profile):
    return None


def _scalar_bar(profile):
    """(bar bits, band bits) for a scalar series: each carries its own calibrated bar
    (`params["z_bar"]`, else the global MIN_ABS_Z), and the band is half a sigma above it."""
    z = profile.params.get("z_bar") or scalar.MIN_ABS_Z
    bar = _z_bits(z)
    return bar, _z_bits(z + NEAR_BAR_Z) - bar


def _select_all(conn, profile):
    return True, None


def _select_scalar(conn, profile):
    """Only the series live scores (shadow.climate and shadow.attention); every other series has
    just the nightly 48 h batch, which a day-by-day walk-forward is not meant to reproduce."""
    key = str(profile.subject_id)
    live = (key.startswith("esphome:") and key.endswith((":Temperature", ":Humidity"))) or key in (
        "attention:switch_count",
        "attention:unlock_count",
    )
    return live, "no live scoring path (nightly 48 h batch only)"


def _select_rates(conn, profile):
    """Only hourly event streams (shadow.live_rates); sender and daily streams are batch only."""
    stream = str(profile.params.get("stream", ""))
    live = profile.params.get("window") == "hour" and stream.startswith("event:")
    return live, "no live scoring path (sender or daily stream, nightly batch only)"


def _select_device(conn, profile):
    """shadow.rhythm skips devices owned by the infrastructure user (they have device_health)."""
    from common.presence_utils import INFRASTRUCTURE_USERNAMES

    cursor = conn.cursor()
    cursor.execute(
        "SELECT u.username FROM device d LEFT JOIN user u ON d.user_id = u.id WHERE d.id = %s",
        (int(profile.subject_id),),
    )
    row = cursor.fetchone()
    owner = row[0] if row else None
    return owner not in INFRASTRUCTURE_USERNAMES, "household hardware: device_health, not rhythm"


def _batch_hour_rows(inferences):
    """Drop the nightly batch rows (`detect_recent`): they are scored by a profile fitted on ALL the
    data including their own hour, so a walk-forward replay is not meant to reproduce them. They
    are the rows whose window is exactly the scored hour."""
    return [
        i
        for i in inferences
        if not (i.window_end and i.window_end - i.window_start == timedelta(hours=1))
    ]


# learner -> how to replay it, compare it and read its stored rows:
#   walk        walk-forward replay at live's cadence: {day: strongest inference}
#   refit       refit a stored profile from the lake as of fitted_to, or None
#   signal      signal of the stored deviation rows
#   day_keyed   stored rows belong to their start day only
#   subject     profile -> the subject key the replay and the stored rows use
#   bar         optional profile -> (bar bits, band bits), for a learner whose bar is per subject
#   select      (conn, profile) -> (live-scored?, reason if not): only live-scored subjects compare
#   days        the days a subject was observed, so "neither" means checked and quiet
#   live_rows   optional filter on the stored rows
#   approximate the replay is an approximation of live's state (declared on the report)
COVERED = {
    presence.NAME: dict(
        walk=walk_presence,
        refit=_refit_presence,
        signal=presence.SIGNAL,
        day_keyed=False,
        subject=_int_subject,
        days=observed_days,
        select=_select_all,
    ),
    stay.NAME: dict(
        walk=walk_stay,
        refit=_refit_stay,
        signal=stay.SIGNAL,
        day_keyed=False,
        subject=_int_subject,
        days=observed_days,
        select=_select_all,
    ),
    daytime.NAME: dict(
        walk=walk_daytime,
        refit=_refit_daytime,
        signal=daytime.SIGNAL,
        day_keyed=True,
        subject=_int_subject,
        days=observed_days,
        select=_select_all,
    ),
    household_day.NAME: dict(
        walk=walk_household,
        refit=None,
        signal="household.day",
        day_keyed=True,
        subject=_household_subject,
        days=None,
        select=_select_all,
    ),
    scalar.NAME: dict(
        walk=walk_scalar,
        refit=None,
        signal=scalar.SIGNAL,
        day_keyed=False,
        subject=_str_subject,
        days=observed_days_scalar,
        live_rows=_batch_hour_rows,
        select=_select_scalar,
        bar=_scalar_bar,
    ),
    rates.NAME: dict(
        walk=walk_rates,
        refit=None,
        signal=rates.SIGNAL,
        day_keyed=False,
        subject=_str_subject,
        days=observed_days_rates,
        select=_select_rates,
    ),
    device_rhythm.NAME: dict(
        walk=walk_device,
        refit=None,
        signal=device_rhythm.SIGNAL_AVAILABILITY,
        day_keyed=False,
        subject=_int_subject,
        days=observed_days_device,
        select=_select_device,
        approximate=True,
    ),
}


def last_data_day(lake_dir):
    grid, _intervals, _users = presence.load_gold(lake_dir)
    days = [r[0] for rows in grid.values() for r in rows if r[4]]
    return max(days) if days else None


def _load_live(conn, learner, signal, subject_id, since):
    from sa import inference_store

    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {inference_store._INFERENCE_COLUMNS} FROM sa_inferences WHERE learner = %s "
        "AND `signal` = %s AND subject_id = %s AND kind = 'deviation' AND computed_at >= %s",
        (learner, signal, str(subject_id), since),
    )
    return [inference_store._inference_from_row(row) for row in cursor.fetchall()]


def _bar_for(name, spec, profile):
    """(bar bits, band bits) for one subject: the learner's own per-subject bar if it has one."""
    if spec.get("bar"):
        return spec["bar"](profile)
    return BAR_BITS.get(name), NEAR_BAR_MARGIN_BITS.get(name, NEAR_BAR_BITS)


def run(lake_dir, conn, since=None, today=None, tz=None, only=None):
    """The parity report: per learner, one record per stored profile and a pooled verdict. `since`
    overrides every learner's matching-inputs date (it can only narrow, never widen, honestly)."""
    from sa import inference_store

    zone = _zone(tz)
    today = today or datetime.now(zone).date()
    horizon = last_data_day(lake_dir)
    reports = []
    for name, spec in COVERED.items():
        if only and name not in only:
            continue
        since_name = (
            max(since, MATCHING_INPUTS_SINCE[name]) if since else MATCHING_INPUTS_SINCE[name]
        )
        span = horizon and window(since_name, horizon, today)
        since_utc = datetime.combine(since_name, datetime.min.time()).replace(tzinfo=zone)
        since_utc = since_utc.astimezone(timezone.utc).replace(tzinfo=None)
        report = {"learner": name, "since": since_name.isoformat(), "subjects": []}
        if spec.get("approximate"):
            report["approximate_replay"] = True
        if not span:
            report["verdict"] = "INSUFFICIENT: no complete day since the matching-inputs date"
            reports.append(report)
            continue
        first, last = span
        report["window"] = {"first": first.isoformat(), "last": last.isoformat()}
        skipped = {}
        for profile in inference_store.load_profiles(conn, name):
            compare, reason = spec["select"](conn, profile)
            if not compare:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            key = spec["subject"](profile)
            subject = "household" if key is None else profile.subject_id
            days = (
                _span(first, last)
                if spec["days"] is None
                else spec["days"](lake_dir, key, first, last)
            )
            rows = _load_live(conn, name, spec["signal"], subject, since_utc)
            if spec.get("live_rows"):
                rows = spec["live_rows"](rows)
            live = live_days(rows, first, last, zone, start_day_only=spec["day_keyed"])
            replayed = spec["walk"](lake_dir, key, first, last, tz)
            record = {"subject": subject, "fitted_to": profile.fitted_to}
            record.update(compare_days(live, replayed, days, *_bar_for(name, spec, profile)))
            if spec["refit"] is not None:
                fresh = spec["refit"](lake_dir, profile, tz)
                record["profile"] = (
                    profile_parity(profile, fresh)
                    if fresh is not None
                    else "refit returned no profile"
                )
            report["subjects"].append(record)
        if skipped:
            report["not_compared"] = skipped
        report["verdict"] = verdict(report["subjects"])
        if spec.get("approximate"):
            report["verdict"] += " [approximate replay]"
        reports.append(report)
    return reports


def main(argv=None):
    """`python -m sa.parity [--since YYYY-MM-DD] [--only learner ...]`: JSON report, read-only."""
    import argparse
    import json
    import os

    from sa import inference_store

    parser = argparse.ArgumentParser(description="Replay-versus-live parity (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    parser.add_argument(
        "--since", type=date.fromisoformat, help="only compare days on or after this date"
    )
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(argv)
    conn = inference_store.connect()
    try:
        reports = run(args.lake, conn, since=args.since, only=args.only)
    finally:
        conn.close()

    def encode(value):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    print(json.dumps(reports, indent=2, default=encode))
    return reports


if __name__ == "__main__":
    main()
