"""Replay harness (Timeline "Context learning 1/5", todo/sa/todo_lf7_replay_harness.md).

Walk-forward replay over the Parquet lake: for every day in a window, a learner is fitted on the
days before it and scored on that day. The learners already know how (each has a `backtest`); this
module runs them under one report format so Phases 3 to 5 can reuse the same evidence:

    {"name", "kind", "window", "evaluations", "flagged", "flag_days", "observed_days",
     "flag_days_per_14", "target_per_14", "by_subject", "unreconstructed", "method"}

Read-only: it opens the lake and nothing else. No database, no Kafka, no network.

Honest about what history cannot give back. A layer-2 rule also reads a calendar and a Deck state,
and the lake cannot reconstruct either for most of the window (calendar free/busy is purged after
each event; Deck network history starts 2026-10-11 and covers two installs). Those inputs are never
invented: the replay runs the rule without them, says so in `unreconstructed`, and where an input
changes the answer it reports both bounds (an empty calendar, a fully booked one).

Flag-day: a local day on which a rule would have raised at least one result at or above the card
confidence floor. The calibration target is about one flag-day in 14 (the household rule's own bar).
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sa import silver
from sa.learners import (
    away_unusual,
    day_off,
    daytime,
    deck_network,
    household_day,
    presence,
    stay,
)

# A published card needs this much confidence (departure_anomaly, climate, ...). Replays count a
# result as flagged when it would have reached a card, not merely when it exists.
CARD_CONFIDENCE_FLOOR = 0.3
TARGET_FLAG_DAYS_PER_14 = 1.0

CALENDAR_UNRECONSTRUCTABLE = (
    "calendar free/busy: the table is purged after each event, so no per-day history exists"
)
DECK_UNRECONSTRUCTABLE = (
    "deck network family: no reporting Deck is linked to anyone with presence data in this window"
)
BRIDGE_HINDSIGHT = (
    "presence intervals are silver as rebuilt today: the learned per-person presence bridge "
    "(deployed 2026-11-01) is applied to the whole window, while live before that date merged "
    "stays with a fixed 45 min bridge. Replays before 2026-11-01 answer 'what would today's code "
    "say', not 'what did live say'; compare against live only on later days"
)
DEVICES_UNRECONSTRUCTABLE = (
    "owned-device rhythm parents: the lake has no owner map in the replay, so corroboration is None"
)


def _day_of(at):
    return at.date() if isinstance(at, datetime) else at


def report(name, kind, start, end, evaluations, unreconstructed=(), method="", extra=None):
    """The shared report. `evaluations` is [{"subject", "at", "flagged", "bits", "confidence"}]; a
    row is one scored moment (an hour, a checkpoint, a day), flagged or not."""
    days = (end - start).days + 1
    observed = {(e["subject"], _day_of(e["at"])) for e in evaluations}
    flagged = [e for e in evaluations if e["flagged"]]
    flag_days = {(e["subject"], _day_of(e["at"])) for e in flagged}
    observed_days = len(observed)
    by_subject = {}
    for subject, day in observed:
        row = by_subject.setdefault(str(subject), {"observed_days": 0, "flag_days": 0})
        row["observed_days"] += 1
        row["flag_days"] += (subject, day) in flag_days
    for row in by_subject.values():
        row["flag_days_per_14"] = _per_14(row["flag_days"], row["observed_days"])
    out = {
        "name": name,
        "kind": kind,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "evaluations": len(evaluations),
        "flagged": len(flagged),
        "observed_days": observed_days,
        "flag_days": len(flag_days),
        "flag_days_per_14": _per_14(len(flag_days), observed_days),
        "target_per_14": TARGET_FLAG_DAYS_PER_14,
        "by_subject": by_subject,
        "unreconstructed": list(unreconstructed),
        "method": method,
    }
    if extra:
        out.update(extra)
    return out


def _per_14(flag_days, observed_days):
    """Flag-days per 14 observed subject-days; None when nothing was observed."""
    if not observed_days:
        return None
    return round(14.0 * flag_days / observed_days, 3)


def _reaches_card(inference):
    return inference is not None and (inference.confidence or 0.0) >= CARD_CONFIDENCE_FLOOR


def _row(subject, at, inference, flagged=None):
    return {
        "subject": subject,
        "at": at,
        "flagged": _reaches_card(inference) if flagged is None else flagged,
        "bits": None if inference is None else inference.surprise,
        "confidence": None if inference is None else inference.confidence,
    }


def _users(lake_dir):
    grid, _intervals, _users = presence.load_gold(lake_dir)
    return sorted(grid)


DECK_RECENT_HOURS = 12  # shadow.deck_network_state reads this much recent history per cycle
DECK_CADENCE_DAYS = 14  # and measures each install's report cadence over this many days


def load_deck(lake_dir):
    """({install: [(observed_at, network_type)]}, {install: user_id}) from the bronze layer: the
    Deck's own network reports and the install-to-user link live uses (the user on the install's
    location fixes). Empty when the lake has neither, so a household without a Deck replays as the
    live rule runs for it: no row, no evidence."""
    import glob
    import os

    import duckdb

    reports_glob = os.path.join(lake_dir, "bronze", "deck_context_history", "date=*", "*.parquet")
    owners_glob = os.path.join(lake_dir, "bronze", "device_location_history", "date=*", "*.parquet")
    if not (glob.glob(reports_glob) and glob.glob(owners_glob)):
        return {}, {}
    con = duckdb.connect()
    try:
        reports = {}
        for install, at, kind in con.execute(
            f"SELECT device_install_id, observed_at, network_type "
            f"FROM read_parquet('{reports_glob}') WHERE network_type IS NOT NULL"
        ).fetchall():
            reports.setdefault(install, []).append((at, kind))
        owners = dict(
            con.execute(
                f"SELECT client_install_id, MAX(user_id) "
                f"FROM read_parquet('{owners_glob}') GROUP BY client_install_id"
            ).fetchall()
        )
        return {i: sorted(r) for i, r in reports.items()}, owners
    finally:
        con.close()


def deck_state_at(deck, user_id, at_utc):
    """The Deck observer's layer-1 state row for `user_id` as live would have written it at
    `at_utc` (naive UTC): sustained cellular or wifi on any of their installs, or None."""
    reports, owners = deck
    for install, owner in owners.items():
        if owner != user_id or install not in reports:
            continue
        history = reports[install]
        recent = [
            r for r in history if at_utc - timedelta(hours=DECK_RECENT_HOURS) <= r[0] <= at_utc
        ]
        cadence = [
            r[0] for r in history if at_utc - timedelta(days=DECK_CADENCE_DAYS) <= r[0] <= at_utc
        ]
        found = deck_network.observe(
            user_id, install, recent, at_utc, deck_network.median_gap_minutes(cadence)
        )
        if found is not None:
            return found
    return None


def replay_away_unusual(lake_dir, start, end, explained_discount=None, with_deck=True):
    """Layer 2 `away_unusual` over the presence backtest: the person's `presence.home` deviation
    fused by the real rule, with the Deck family reconstructed from the bronze layer for people
    whose Deck reports (sustained cellular corroborates, sustained wifi explains the absence away).
    Calendar and owned-device parents are not reconstructed (see module doc). `explained_discount`
    sweeps the share of surprise an explanation removes; in this replay only the Deck's wifi
    state explains, so it calibrates that discount without touching the calendar's."""
    from sa import layer2

    rule = away_unusual.AwayUnusualRule()
    if explained_discount is not None:
        rule.explained_discount = explained_discount
    deck = load_deck(lake_dir) if with_deck else ({}, {})
    rows, plain_rows, by_state = [], [], {"out": 0, "wifi": 0, "none": 0}
    zone = ZoneInfo(silver.TIMEZONE)
    for user in _users(lake_dir):
        for hit in presence.backtest(lake_dir, user, start, end, hours=range(6, 23)):
            inference = hit["inference"]
            if inference is None:
                rows.append(_row(user, hit["at_local"], None))
                plain_rows.append(_row(user, hit["at_local"], None))
                continue
            at_utc = (
                hit["at_local"].replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
            )
            profile = hit["profile"]
            plain = away_unusual.combine(
                str(user), profile.params.get("username"), inference, [], 0, hit["at_local"]
            )
            plain_rows.append(_row(user, hit["at_local"], plain))
            state = deck_state_at(deck, user, at_utc)
            parents = [inference] + ([state] if state is not None else [])
            fused = layer2.run_rules(
                [rule], parents, {"owners": {}, "owned_with_profile": {}}, hit["at_local"]
            )
            by_state[(state.observed or {}).get("state", "none") if state else "none"] += 1
            rows.append(_row(user, hit["at_local"], fused[0] if fused else None))
    users_with_deck = len({o for o in deck[1].values() if o in set(_users(lake_dir))})
    without = report("x", "layer2", start, end, plain_rows)
    return report(
        away_unusual.NAME,
        "layer2",
        start,
        end,
        rows,
        unreconstructed=[CALENDAR_UNRECONSTRUCTABLE, DEVICES_UNRECONSTRUCTABLE]
        + ([] if users_with_deck else [DECK_UNRECONSTRUCTABLE]),
        method="presence backtest (hourly 06-22 local) fused by AwayUnusualRule with the Deck "
        "network state reconstructed from bronze deck_context_history",
        extra={
            "deck": {
                "users_with_a_reporting_deck": users_with_deck,
                "presence_deviations_by_deck_state": by_state,
                "flag_days_without_deck": without["flag_days"],
                "flag_days_with_deck": len(
                    {(r["subject"], _day_of(r["at"])) for r in rows if r["flagged"]}
                ),
            },
            "explained_discount": rule.explained_discount,
        },
    )


def replay_day_off(lake_dir, start, end, corroboration_floor=None):
    """Layer 2 `day_off` over the daytime backtest. The calendar corroborates (share) but cannot be
    replayed, so each result is fused under three calendar states: unknown (None, as the live rule
    runs without a count), an empty day (share 1.0) and a fully booked one (share 0.0). The empty
    calendar is the upper bound of flag-days; the booked one, with the 0.3 floor, the lower."""
    rule = day_off.DayOffRule()
    if corroboration_floor is not None:
        rule.corroboration_floor = corroboration_floor
    states = {"unknown": None, "empty_calendar": 0, "booked_calendar": 1}
    rows = {key: [] for key in states}
    for user in _users(lake_dir):
        for hit in daytime.backtest(lake_dir, user, start, end):
            parent = hit["inference"]
            if parent is None:
                continue
            for key, events in states.items():
                ctx = {"day_start_utc": None, "calendar_events_today": events}
                for group in rule.groups([parent], ctx):
                    fused = _fuse(rule, group, parent)
                    rows[key].append(_row(user, hit["date"], fused))
    primary = rows["unknown"]
    extra = {
        "calendar_bounds": {
            key: {
                "flag_days": len({(e["subject"], e["at"]) for e in found if e["flagged"]}),
                "observed_days": len({(e["subject"], e["at"]) for e in found}),
            }
            for key, found in rows.items()
        },
        "corroboration_floor": rule.corroboration_floor,
    }
    return report(
        day_off.NAME,
        "layer2",
        start,
        end,
        primary,
        unreconstructed=[CALENDAR_UNRECONSTRUCTABLE],
        method="daytime backtest (13:00 and 17:00 checkpoints) fused by DayOffRule",
        extra=extra,
    )


def _fuse(rule, group, parent):
    from sa import layer2

    return layer2.fuse(rule, group, parent.window_start)


def replay_household_day(lake_dir, start, end):
    """Layer 2 `household_unusual_day`: the learner backtest already applies its own calibrated bar
    (about one day in 14), so a flag here is the live rule's flag. No card floor on top."""
    rows = [
        {
            "subject": "household",
            "at": hit["date"],
            "flagged": bool(hit["flagged"]),
            "bits": hit["bits"],
            "confidence": None,
        }
        for hit in household_day.backtest(lake_dir, start, end)
    ]
    return report(
        household_day.NAME,
        "layer2",
        start,
        end,
        rows,
        unreconstructed=[],
        method="household_day.backtest: bar calibrated on the days before each day",
    )


def replay_stay(lake_dir, start, end):
    """Layer 1 `stay` (the source of the `departure_anomaly` card): hourly deviation, counted at the
    card confidence floor."""
    rows = []
    for user in _users(lake_dir):
        for hit in stay.backtest(lake_dir, user, start, end, hours=range(6, 23)):
            rows.append(_row(user, hit["at_local"], hit["inference"]))
    return report(
        stay.NAME,
        "layer1",
        start,
        end,
        rows,
        unreconstructed=[BRIDGE_HINDSIGHT],
        method="stay backtest (hourly 06-22 local, only when home)",
    )


REPLAYS = {
    "away_unusual": replay_away_unusual,
    "day_off": replay_day_off,
    "household_unusual_day": replay_household_day,
    "stay": replay_stay,
}


def sweep(fn, lake_dir, start, end, parameter, values):
    """Run one replay across candidate values of a constant, to calibrate it from observed rates.
    Only parameters a replay function accepts are sweepable (`corroboration_floor` for day_off).
    Returns [{"value", "flag_days", "flag_days_per_14"}]. Never changes the live constant."""
    out = []
    for value in values:
        result = fn(lake_dir, start, end, **{parameter: value})
        out.append(
            {
                "value": value,
                "flag_days": result["flag_days"],
                "flag_days_per_14": result["flag_days_per_14"],
            }
        )
    return out


def run(lake_dir, start, end, names=None):
    """Every replay (or the named ones) over [start, end], as a list of reports."""
    chosen = names or list(REPLAYS)
    unknown = [n for n in chosen if n not in REPLAYS]
    if unknown:
        raise ValueError(f"unknown replay: {', '.join(unknown)}; known: {', '.join(REPLAYS)}")
    return [REPLAYS[name](lake_dir, start, end) for name in chosen]


def default_window(today=None, days=28):
    """The last `days` complete local days: yesterday back."""
    end = (today or date.today()) - timedelta(days=1)
    return end - timedelta(days=days - 1), end


def _jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not serialisable: {type(value)}")


def main(argv=None):
    """`python -m sa.replay [--days N | --start D --end D] [--only name ...] [--sweep]`: one
    command reproduces the replay on a fixed window. Prints the reports as JSON."""
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description="Walk-forward replay over the SA lake (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--sweep", action="store_true", help="also sweep the day_off floor")
    args = parser.parse_args(argv)
    if args.start and args.end:
        start, end = args.start, args.end
    else:
        start, end = default_window(days=args.days)
    reports = run(args.lake, start, end, args.only)
    if args.sweep:
        reports.append(
            {
                "name": "away_unusual.explained_discount_sweep",
                "sweep": sweep(
                    replay_away_unusual,
                    args.lake,
                    start,
                    end,
                    "explained_discount",
                    [0.5, 0.7, 0.9],
                ),
            }
        )
        reports.append(
            {
                "name": "day_off.corroboration_floor_sweep",
                "sweep": sweep(
                    replay_day_off,
                    args.lake,
                    start,
                    end,
                    "corroboration_floor",
                    [0.3, 0.5, 0.7, 1.0],
                ),
            }
        )
    print(json.dumps(reports, indent=2, default=_jsonable))
    return reports


if __name__ == "__main__":
    main()
