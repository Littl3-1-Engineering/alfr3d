"""Shadow proposals (Layer 3, step 2 of the order in todo/sa/todo_l3_executor_spec.md).

What would Layer 3 have proposed, and how would it have turned out? This replays the proof
predictor (`sa/predictors.py`, `switch_usual_state`) over the past: for each recent day it fits the
predictor on the days BEFORE that day only, and at the start of every hour asks whether it would
have proposed turning a switch on (usually on now, off at the moment) or off (usually off now, on at
the moment). Each would-be proposal is then labelled by `sa/outcomes.label_action` against what the
household actually did in the next hour (the state history, whoever changed it), and the counts go
through `sa/proposals.recommend` exactly as a real promotion screen would see them.

It is a **retrospective, read-only replay**: no card is made, nothing is stored, no command is
issued, and the module imports nothing that can reach a device. It exists because a new visible
card needs the Deck and the web frontend to render it, and the evidence about whether proposals are
worth showing at all is available now without either.

The honest comparison is the base rate. A proposal "was acted on" if the lamp turned on within the
hour, but a lamp turns on within the hour often anyway; the report gives that rate for the same
hours so the lift (or its absence) is visible. Autonomous commands are excluded as everywhere else.
"""

import argparse
import bisect
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sa import outcomes, predictors, proposals

# Placeholders, as in the card rules: a proposal needs a confident, extreme probability.
HIGH = 0.85  # usually on at this hour: propose switch_on if it is off
LOW = 0.10  # usually off at this hour: propose switch_off if it is on
MIN_CONFIDENCE = 0.3  # the same bar as a card (learners/presence.MIN_CARD_CONFIDENCE)
COOLDOWN_HOURS = 3  # no repeat of the same proposal for the same switch inside this many hours
DEFAULT_DAYS = 14

_ON, _OFF = "on", "off"


def state_at(events, when):
    """'on', 'off' or None (nothing observed yet) for the last event at or before `when`.
    `events`: [(time, state)] sorted, naive UTC."""
    i = bisect.bisect_right([t for t, _ in events], when)
    return events[i - 1][1] if i else None


def _hour_start_utc(day, hour, tz):
    local = datetime(day.year, day.month, day.day, hour, tzinfo=tz)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _changes_within(events, start, state, window):
    stop = start + window
    return any(start <= t <= stop and s == state for t, s in events)


def replay_switch(entity, transitions, end, zone, autonomy=(), days=DEFAULT_DAYS):
    """The shadow replay for one switch: {"entity", "status", "evidence", "recommendation",
    "proposed", "baseline"}. `status` is `no_proposals` when the predictor stayed silent (not
    enough history, or it did not beat the usual rate), else `replayed`."""
    tz = ZoneInfo(zone) if isinstance(zone, str) else zone
    rows = predictors.hourly_states(transitions, end, tz, autonomy=autonomy)
    events = sorted((t, s) for t, s in transitions if s in (_ON, _OFF))
    window = timedelta(minutes=outcomes.ACTION_TYPES["switch_on"].window_minutes)
    eval_days = sorted({d for d, *_ in rows})[-days:]
    labelled, proposed, spoke_days = [], [], 0
    base = {"switch_on": [0, 0], "switch_off": [0, 0]}  # [hours, hours the change happened anyway]
    last_at = {}
    for day in eval_days:
        train = [r for r in rows if r[0] < day]  # only what was known before this day
        score = predictors.evaluate(train)
        if score["status"] != "scored" or score["skill"] < predictors.MIN_SKILL:
            continue
        spoke_days += 1
        kind = predictors.day_kind(day)
        for hour in range(24):
            at = _hour_start_utc(day, hour, tz)
            if at + window > end:
                continue  # the outcome is not knowable yet
            state = state_at(events, at)
            if state is None:
                continue
            action, expected = ("switch_on", _ON) if state == _OFF else ("switch_off", _OFF)
            base[action][0] += 1
            base[action][1] += _changes_within(events, at, expected, window)
            prediction = predictors.predict(train, entity, hour, kind)
            if prediction is None or prediction.confidence < MIN_CONFIDENCE:
                continue
            wants = (
                prediction.probability >= HIGH
                if expected == _ON
                else (prediction.probability <= LOW)
            )
            if not wants:
                continue
            if action in last_at and at - last_at[action] < timedelta(hours=COOLDOWN_HOURS):
                continue
            last_at[action] = at
            label, cause, _basis = outcomes.label_action(action, at, expected, events, end)
            labelled.append((label, cause))
            proposed.append(
                {
                    "at": at.isoformat(),
                    "action": action,
                    "p": prediction.probability,
                    "label": label,
                }
            )
    evidence = outcomes.evidence_from_labels(labelled)
    return {
        "entity": entity,
        "status": "replayed" if evidence["proposals"] else "no_proposals",
        "days_the_predictor_spoke": spoke_days,
        "evidence": evidence,
        "recommendation": proposals.recommend(evidence),
        "proposed": proposed,
        "baseline": {
            action: {
                "hours": hours,
                "happened_anyway": hit,
                "rate": round(hit / hours, 4) if hours else None,
            }
            for action, (hours, hit) in base.items()
        },
    }


def replay_lake(lake_dir, zone=None, days=DEFAULT_DAYS):
    """{"switches": [...], "total": evidence summed, "note": ...} over the lake. Read-only."""
    from sa import silver

    by_entity, end = predictors.load_switch_history(lake_dir)
    zone = zone or silver.TIMEZONE
    own = predictors.autonomy_commands(lake_dir)
    switches = [
        replay_switch(e, trs, end, zone, own.get(e, ()), days)
        for e, trs in sorted(by_entity.items())
    ]
    keys = ("proposals", "acted_on", "acted_on_alfr3d", "undone", "rejected", "ignored")
    total = {k: sum(s["evidence"][k] for s in switches) for k in keys}
    return {
        "window_days": days,
        "switches": switches,
        "total": total,
        "recommendation": proposals.recommend(total),
        "note": "a retrospective replay: nothing was shown, stored or commanded. Compare the "
        "acted-on share with each switch's baseline rate before reading it as skill.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shadow proposals over the lake (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = parser.parse_args(argv)
    report = replay_lake(args.lake, days=args.days)
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
