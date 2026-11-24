"""Outcome labels (Layer 3 1/4, Phase 6a; todo/sa/todo_l3_outcomes_predictors.md).

Nothing can earn autonomy without knowing how its past proposals ended. Every card and every future
proposal ends in exactly one of four outcomes, linked to the event that proves it:

    acted_on   the household did what it suggested (or engaged with it)
    ignored    it was seen or expired and nothing came of it
    undone     an action Alfr3d performed was reversed by a person (only level 2 and 3 can be)
    rejected   the household said no, or that it was not useful

plus `pending` while the answer cannot be known yet. This module only DEFINES the labels and counts
them; it executes nothing, writes nothing and changes no card. A label is a pure function of
recorded events, so a replay over the past reports the same counts live would.

Two label families, because the evidence differs:

- **Cards** (`label_card`): from `card_interactions`, using the semantics the API already documents.
  `tapped` is engagement and `acked` ("got it", a mild positive) are `acted_on`; `dismissed` is a
  swipe-away, "seen, no comment", so `ignored`; `not_useful` is the one clearly negative action, so
  `rejected`. Negative wins if both occur: a demotion must never be missed. A card with no outcome
  past its TTL is `ignored`.
- **Device proposals** (`label_action`): from the state change the proposal predicted, WHOEVER
  caused it. Alfr3d's API is not the only way a switch changes (49 of 168 transitions in the last
  18 days had no API command: a wall switch or an automation), so "acted on" is the predicted change
  appearing in the state history inside the action type's window, with the cause recorded
  (`household` or `alfr3d`). There are no proposals yet, so this is specified and tested on
  synthetic history, not measured on real outcomes: the real ones start with the first proposals.

Window and undo length are per action type (`ACTION_TYPES`), so a new proposal type inherits the
labelling by registration.
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sa.sqlutil import sql_str

ACTED_ON, IGNORED, UNDONE, REJECTED, PENDING = (
    "acted_on",
    "ignored",
    "undone",
    "rejected",
    "pending",
)
LABELS = (ACTED_ON, IGNORED, UNDONE, REJECTED, PENDING)

CARD_TTL_HOURS = 24  # a card with no outcome this long after its impression was ignored
POSITIVE = ("tapped", "acked")
NEUTRAL = ("dismissed", "expired")
NEGATIVE = ("not_useful",)


@dataclass(frozen=True)
class ActionType:
    """What counts as 'acted on' and 'undone' for one kind of proposal."""

    key: str
    window_minutes: int  # how long after a proposal the predicted change still counts
    undo_minutes: int  # how long after Alfr3d acted a reversal still counts as an undo
    description: str = ""


# The first types opened (owner decision, 2026-11-18): on/off of lights and switches. A starting
# row, not a hard-coded feature: any other action type is one more registration.
ACTION_TYPES = {
    "switch_on": ActionType("switch_on", 60, 30, "turn a switch or light on"),
    "switch_off": ActionType("switch_off", 60, 30, "turn a switch or light off"),
}


def label_card(actions, age_hours):
    """(label, basis) for one card impression from the actions recorded against it. `actions`: the
    action names (`tapped`, `acked`, `dismissed`, `expired`, `not_useful`) of the interaction rows
    that share its impression; `age_hours`: hours since the impression."""
    seen = set(actions)
    if seen & set(NEGATIVE):
        return REJECTED, "not_useful"
    if seen & set(POSITIVE):
        return ACTED_ON, "tapped" if "tapped" in seen else "acked"
    if seen & set(NEUTRAL):
        return IGNORED, "dismissed" if "dismissed" in seen else "expired"
    if age_hours >= CARD_TTL_HOURS:
        return IGNORED, "no outcome within the TTL"
    return PENDING, "no outcome yet"


def label_action(
    action_type,
    proposed_at,
    expected_state,
    transitions,
    now,
    declined=False,
    performed_by=None,
    reverted_by_person=None,
):
    """(label, cause, basis) for one device proposal.

    `transitions`: [(time, state)] of that entity, whoever caused each; `expected_state`: the state
    the proposal predicted ("on"/"off"); `declined`: the household explicitly said no;
    `performed_by`: "alfr3d" if Alfr3d itself made the change (levels 2 and 3), else None;
    `reverted_by_person`: time of a reversal by a person, if any."""
    kind = ACTION_TYPES[action_type]
    window_end = proposed_at + timedelta(minutes=kind.window_minutes)
    if declined:
        return REJECTED, None, "declined"
    hit = next(
        (
            t
            for t, s in sorted(transitions)
            if proposed_at <= t <= window_end and s == expected_state
        ),
        None,
    )
    if hit is None:
        return (
            (PENDING, None, "window still open")
            if now < window_end
            else (
                IGNORED,
                None,
                "predicted change did not happen in the window",
            )
        )
    cause = "alfr3d" if performed_by == "alfr3d" else "household"
    if cause == "alfr3d" and reverted_by_person is not None:
        if hit <= reverted_by_person <= hit + timedelta(minutes=kind.undo_minutes):
            return UNDONE, cause, "reversed by a person inside the undo window"
    return ACTED_ON, cause, "predicted change happened"


def evidence_from_labels(labelled):
    """The counts a promotion decision is shown, from [(label, cause)] pairs (`label_action`'s
    first two fields). Pending is not decided yet, so it is not counted. `acted_on_alfr3d` is the
    part of `acted_on` that Alfr3d did itself: `proposals.recommend` does not count it as approval.
    """
    counts = Counter()
    for label, cause in labelled:
        if label == PENDING:
            continue
        counts["proposals"] += 1
        counts[label] += 1
        if label == ACTED_ON and cause == "alfr3d":
            counts["acted_on_alfr3d"] += 1
    keys = ("proposals", ACTED_ON, "acted_on_alfr3d", UNDONE, REJECTED, IGNORED)
    return {k: counts.get(k, 0) for k in keys}


# --- Replay over the lake (read-only) --------------------------------------------------------


def load_cards(lake_dir):
    """[(rule_id, action, impression_id, occurred_at, user_id, surface)] from the bronze
    `card_interactions`, oldest first. Empty when the lake has none."""
    import duckdb

    pattern = os.path.join(lake_dir, "bronze", "card_interactions", "date=*", "*.parquet")
    if not glob.glob(pattern):
        return []
    con = duckdb.connect()
    try:
        return con.execute(
            f"SELECT rule_id, action, impression_id, occurred_at, user_id, surface "
            f"FROM read_parquet({sql_str(pattern)}, union_by_name=true) ORDER BY occurred_at"
        ).fetchall()
    finally:
        con.close()


def card_report(rows, start, end, now=None):
    """Counts of outcome labels per rule for impressions in [start, end] (naive UTC dates).

    Only `impression` rows are cards that were actually shown (the repeating `shown` rows are the
    awareness loop logging its own cycles). An explicit outcome that carries no impression id (older
    rows) cannot be linked to an impression; those are counted separately, never guessed at."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    impressions, outcomes, unlinked = {}, defaultdict(list), Counter()
    for rule, action, imp_id, at, _user, _surface in rows:
        day = at.date()
        if action == "impression" and imp_id and start <= day <= end:
            impressions[imp_id] = (rule, at)
        elif action in POSITIVE + NEUTRAL + NEGATIVE:
            if imp_id:
                outcomes[imp_id].append(action)
            elif start <= day <= end:
                unlinked[(rule, action)] += 1
    per_rule = defaultdict(Counter)
    for imp_id, (rule, at) in impressions.items():
        label, _basis = label_card(outcomes.get(imp_id, ()), (now - at).total_seconds() / 3600.0)
        per_rule[rule][label] += 1
    return {
        "window": [start.isoformat(), end.isoformat()],
        "impressions": len(impressions),
        "per_rule": {
            rule: {
                **{label: counts.get(label, 0) for label in LABELS},
                "total": sum(counts.values()),
            }
            for rule, counts in sorted(per_rule.items())
        },
        "explicit_outcomes_without_an_impression_id": {
            f"{rule}:{action}": n for (rule, action), n in sorted(unlinked.items())
        },
        "note": "labels are definitions applied to recorded events; no proposal exists yet, so no "
        "undone outcomes and no device-action outcomes are measured here",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Card outcome labels over the lake (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    parser.add_argument("--days", type=int, default=56, help="window length, ending yesterday")
    args = parser.parse_args(argv)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    report = card_report(load_cards(args.lake), start, end)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
