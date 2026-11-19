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
  `since` date (default `MATCHING_INPUTS_SINCE`); advance it after any change to a learner or to
  silver, never backwards.
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

Read-only: lake and database reads, no writes. Covered: presence, stay, daytime and household_day.
Not yet: device_rhythm, scalar, rates, drift (their backtests take a series or device key).
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sa import replay, silver
from sa.learners import daytime, household_day, presence, stay

# Silver and the stay learner last changed on 2026-11-01 (the learned presence bridge, PR #365).
# Advance this after any later change to a learner or to silver; it must never move backwards.
MATCHING_INPUTS_SINCE = date(2026, 11, 1)
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


def observed_days(lake_dir, user_id, first, last):
    """Days in range on which this person has a (nearly) complete observed day in the gold grid, so
    a 'neither' day means 'checked and quiet', not 'no data'."""
    grid, _i, _u = presence.load_gold(lake_dir)
    seen = {}
    for d, _h, _dw, _m, ok in grid.get(user_id, []):
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


def compare_days(live, replayed, days):
    """Classify every comparable day. Returns the parity record for one (learner, subject)."""
    outcomes = {"both": 0, "live_only": 0, "replay_only": 0, "neither": 0}
    mismatches, pairs, flips = [], [], []
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
        outcomes[kind] += 1
        if kind in ("live_only", "replay_only"):
            mismatches.append(
                {
                    "day": day.isoformat(),
                    "kind": kind,
                    "live": live.get(day),
                    "replay": replayed.get(day),
                }
            )
    return {
        "comparable_days": len(days),
        "outcomes": outcomes,
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
    if both == 0:
        return "MATCH (neither side flagged anything: agreement on quiet days only)"
    return "MATCH"


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


# learner -> (walk-forward replay, refit for profile parity or None, signal of the stored rows,
# whether the stored rows are keyed to one day)
COVERED = {
    presence.NAME: (walk_presence, _refit_presence, presence.SIGNAL, False),
    stay.NAME: (walk_stay, _refit_stay, stay.SIGNAL, False),
    daytime.NAME: (walk_daytime, _refit_daytime, daytime.SIGNAL, True),
    household_day.NAME: (walk_household, None, "household.day", True),
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


def run(lake_dir, conn, since=None, today=None, tz=None, only=None):
    """The parity report: per learner, one record per stored profile and a pooled verdict."""
    from sa import inference_store

    zone = _zone(tz)
    since = since or MATCHING_INPUTS_SINCE
    today = today or datetime.now(zone).date()
    horizon = last_data_day(lake_dir)
    span = horizon and window(since, horizon, today)
    since_utc = datetime.combine(since, datetime.min.time()).replace(tzinfo=zone)
    since_utc = since_utc.astimezone(timezone.utc).replace(tzinfo=None)
    reports = []
    for name, (walk, refit, signal, day_keyed) in COVERED.items():
        if only and name not in only:
            continue
        report = {"learner": name, "since": since.isoformat(), "subjects": []}
        if not span:
            report["verdict"] = "INSUFFICIENT: no complete day since the matching-inputs date"
            reports.append(report)
            continue
        first, last = span
        report["window"] = {"first": first.isoformat(), "last": last.isoformat()}
        for profile in inference_store.load_profiles(conn, name):
            household = name == household_day.NAME
            subject = "household" if household else profile.subject_id
            uid = None if household else int(profile.subject_id)
            days = _span(first, last) if household else observed_days(lake_dir, uid, first, last)
            rows = _load_live(conn, name, signal, subject, since_utc)
            live = live_days(rows, first, last, zone, start_day_only=day_keyed)
            record = {"subject": subject, "fitted_to": profile.fitted_to}
            record.update(compare_days(live, walk(lake_dir, uid, first, last, tz), days))
            if refit is not None:
                fresh = refit(lake_dir, profile, tz)
                record["profile"] = (
                    profile_parity(profile, fresh)
                    if fresh is not None
                    else "refit returned no profile"
                )
            report["subjects"].append(record)
        report["verdict"] = verdict(report["subjects"])
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
    parser.add_argument("--since", type=date.fromisoformat, default=MATCHING_INPUTS_SINCE)
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
