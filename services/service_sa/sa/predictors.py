"""Predictor registry (Layer 3 2/4, Phase 6b; todo/sa/todo_l3_outcomes_predictors.md).

Layer 3 anticipates: what happens next, what would help. A predictor is declared once, here, and
says what it predicts, from which history, and what evidence it needs before it may speak. It uses
conditional frequency counts (no black box), is validated on a time-ordered held-out block, carries
a probability, a confidence from the shared layer-1 contract (`sa/confidence.py`) and a `because`
list, and is scored on how often it was right. Below its floors it says "insufficient evidence"
and nothing else. Weather, calendar, indoor climate or location join later as features through the
covariate engine and the discovery screen, not as special cases here.

**Nothing here acts.** A prediction is data. No card is made from it, nothing reads it yet, and no
device command is issued: layer 3's executor is a later phase behind the owner's approval, and this
module has no import that could reach a device.

One proof predictor ships, `switch_usual_state`: for a switch or light, how likely is it to be ON at
a given local hour on a given kind of day (weekday or weekend)? The training signal is the state
history Home Assistant keeps, **whoever changed the state**: Alfr3d's own commands are only part of
it (49 of 168 transitions in the 18 days measured had no API command, a wall switch or an
automation), so the predictor learns what the household does, not what the API did.

It is deliberately small: with weeks, not months, of history it can describe a regular lamp and say
nothing about an irregular one. The floors make that explicit.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from sa.sqlutil import sql_str
from sa import confidence as confidence_contract

HOUR = timedelta(hours=1)

# Floors: below them the predictor reports "insufficient evidence" instead of a number.
MIN_TRAIN_DAYS = 10
MIN_TEST_HOURS = 72
# A predictor must beat "always the usual rate" by a real margin on the held-out block, not by
# rounding noise: the same reasoning as the covariate engine's 10 % gain bar.
MIN_SKILL = 0.10
TRAIN_FRACTION = 0.7
# A cell (hour x day kind) with this few comparable days borrows heavily from its parent.
PRIOR_WEIGHT = 2.0
ON_FRACTION = 0.5  # an hour counts as "on" when the switch was on for at least half of it
# Confidence terms (sa/confidence.py): every one is required, none defaults to 1.0.
SOURCE_QUALITY = 0.8  # HA keeps true state changes (sub-second last_changed, assumed, not proven)
WEEKDAY, WEEKEND = "weekday", "weekend"


@dataclass(frozen=True)
class Predictor:
    key: str
    description: str
    predicts: str  # what the probability is the probability OF
    history: str  # where the training signal comes from
    min_train_days: int = MIN_TRAIN_DAYS
    min_test_hours: int = MIN_TEST_HOURS


REGISTRY = (
    Predictor(
        key="switch_usual_state",
        description="Is this switch or light usually on at this hour, on this kind of day?",
        predicts="the switch is ON for at least half of the local hour",
        history="Home Assistant state history of the switch (any cause), hourly",
    ),
)


@dataclass
class Prediction:
    predictor: str
    subject: str
    hour_local: int
    day_kind: str
    probability: float
    confidence: float
    because: list
    n_days: int


def day_kind(local_date):
    return WEEKEND if local_date.weekday() >= 5 else WEEKDAY


AUTONOMY_MATCH_SECONDS = 120  # a state change this soon after a matching command was its effect


def _autonomy_intervals(events, autonomy, end):
    """[(start, stop)] spans of state that Alfr3d's own autonomous commands caused: from each
    transition that follows a matching command to the next transition of any cause (or `end`)."""
    spans = []
    for i, (t, state) in enumerate(events):
        caused = any(
            cs == state and 0 <= (t - ct).total_seconds() <= AUTONOMY_MATCH_SECONDS
            for ct, cs in autonomy
        )
        if caused:
            spans.append((t, events[i + 1][0] if i + 1 < len(events) else end))
    return spans


def hourly_states(transitions, end, zone, autonomy=()):
    """[(date_local, hour_local, day_kind, on_fraction)] for one switch, from `transitions`
    ((time, 'on'|'off') in naive UTC, any order) up to `end` (naive UTC). The state before the first
    observation is unknown, so the series starts at the first observed transition's hour.

    `autonomy` is [(time, 'on'|'off')] of commands Alfr3d issued under its own autonomy. The state
    such a command caused is excluded (every hour it touches, through the next change of state,
    whoever made it): otherwise a lamp the executor turns on at 19:00 would teach the predictor to
    turn it on at 19:00, and the prediction would improve each time it acted."""
    events = sorted((t, s) for t, s in transitions if s in ("on", "off"))
    if not events:
        return []
    spans = _autonomy_intervals(events, sorted(autonomy), end) if autonomy else []
    tz = ZoneInfo(zone) if isinstance(zone, str) else zone
    start = events[0][0].replace(minute=0, second=0, microsecond=0)
    out, state, i, bucket = [], None, 0, start
    while bucket < end:
        nxt = bucket + HOUR
        on_seconds, cursor = 0.0, bucket
        while i < len(events) and events[i][0] < nxt:
            t, s = events[i]
            if state == "on" and t > cursor:
                on_seconds += (t - cursor).total_seconds()
            cursor, state, i = max(cursor, t), s, i + 1
        if state == "on":
            on_seconds += (nxt - cursor).total_seconds()
        local = bucket.replace(tzinfo=timezone.utc).astimezone(tz)
        if not any(bucket < stop and nxt > begin for begin, stop in spans):
            out.append((local.date(), local.hour, day_kind(local.date()), on_seconds / 3600.0))
        bucket = nxt
    return out


def _fit(rows):
    """Counts by (hour, day kind), by hour and overall from training rows."""
    cell, hour, total = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), [0, 0]
    days = defaultdict(set)
    for d, h, kind, frac in rows:
        on = 1 if frac >= ON_FRACTION else 0
        for counts in (cell[(h, kind)], hour[h], total):
            counts[0] += on
            counts[1] += 1
        days[(h, kind)].add(d)
    return cell, hour, total, days


def _p(model, h, kind):
    """Smoothed P(on): the (hour, day kind) cell pulled toward the hour, pulled toward the overall
    rate, so a cell with few comparable days cannot claim certainty."""
    cell, hour, total, _ = model
    overall = total[0] / total[1] if total[1] else 0.0
    n_h = hour[h][1] if h in hour else 0
    p_hour = (hour[h][0] + PRIOR_WEIGHT * overall) / (n_h + PRIOR_WEIGHT) if n_h else overall
    c = cell.get((h, kind), [0, 0])
    return (c[0] + PRIOR_WEIGHT * p_hour) / (c[1] + PRIOR_WEIGHT)


def evaluate(rows, predictor=REGISTRY[0]):
    """Time-blocked held-out score for one switch's hourly `rows`, as a dict:
    {"status": "scored" | "insufficient_evidence", "reason", "train_days", "test_hours",
    "brier", "baseline_brier", "skill"}. Fitted on the first 70 % of days, judged on the rest; the
    baseline always predicts the training on-rate. Skill is 1 - brier / baseline_brier."""
    days = sorted({d for d, *_ in rows})
    cut = int(len(days) * TRAIN_FRACTION)
    train_days, test_days = set(days[:cut]), set(days[cut:])
    train = [r for r in rows if r[0] in train_days]
    test = [r for r in rows if r[0] in test_days]
    out = {"train_days": len(train_days), "test_hours": len(test)}
    if len(train_days) < predictor.min_train_days:
        return {
            **out,
            "status": "insufficient_evidence",
            "reason": f"only {len(train_days)} training days (need {predictor.min_train_days})",
        }
    if len(test) < predictor.min_test_hours:
        return {
            **out,
            "status": "insufficient_evidence",
            "reason": f"only {len(test)} held-out hours (need {predictor.min_test_hours})",
        }
    model = _fit(train)
    overall = model[2][0] / model[2][1]
    brier = base = 0.0
    for _d, h, kind, frac in test:
        y = 1.0 if frac >= ON_FRACTION else 0.0
        brier += (y - _p(model, h, kind)) ** 2
        base += (y - overall) ** 2
    brier, base = brier / len(test), base / len(test)
    skill = 1.0 - brier / base if base > 0 else 0.0
    return {
        **out,
        "status": "scored",
        "brier": round(brier, 4),
        "baseline_brier": round(base, 4),
        "skill": round(skill, 4),
    }


def predict(rows, subject, hour_local, kind, predictor=REGISTRY[0]):
    """The Prediction for one switch at (hour, day kind), or None when the held-out score is
    insufficient evidence or shows less than MIN_SKILL over the baseline (a predictor that does not
    beat "always the usual rate" has nothing to say). Fitted on ALL the rows once it is validated.
    """
    score = evaluate(rows, predictor)
    if score["status"] != "scored" or score["skill"] < MIN_SKILL:
        return None
    model = _fit(rows)
    cell = model[0].get((hour_local, kind), [0, 0])
    days_seen = len(model[3].get((hour_local, kind), ()))
    days_all = len({d for d, *_ in rows})
    p = _p(model, hour_local, kind)
    conf = confidence_contract.Confidence(
        sufficiency=confidence_contract.sufficiency(cell[1]),
        coverage=min(1.0, days_seen / max(1, days_all)) if days_all else 0.0,
        source_quality=SOURCE_QUALITY,
        stability=max(0.0, min(1.0, score["skill"])),
    )
    because = [
        f"on in {cell[0]} of {cell[1]} comparable {kind} hours at {hour_local:02d}:00",
        f"held-out skill {score['skill']:.2f} over the usual rate "
        f"(Brier {score['brier']} against {score['baseline_brier']}, {score['test_hours']} hours)",
    ]
    return Prediction(
        predictor=predictor.key,
        subject=subject,
        hour_local=hour_local,
        day_kind=kind,
        probability=round(p, 4),
        confidence=round(conf.value, 4),
        because=because,
        n_days=days_seen,
    )


def autonomy_commands(lake_dir):
    """{entity: [(time, 'on'|'off')]} of successful commands issued with origin `autonomy`, from
    the lake's `device_command_history` (naive UTC). Empty when there are none. Read-only."""
    import glob
    import os

    import duckdb

    pattern = os.path.join(lake_dir, "bronze", "device_command_history", "date=*", "*.parquet")
    if not glob.glob(pattern):
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT entity_ref, command, issued_at FROM read_parquet({sql_str(pattern)}, "
            f"union_by_name=true) WHERE origin = 'autonomy' AND CAST(success AS INTEGER) = 1 "
            f"AND command IN ('turn_on', 'turn_off') ORDER BY entity_ref, issued_at"
        ).fetchall()
    finally:
        con.close()
    out = defaultdict(list)
    for entity, command, at in rows:
        out[entity].append((at.replace(tzinfo=None), "on" if command == "turn_on" else "off"))
    return dict(out)


def load_switch_history(lake_dir):
    """({entity: [(time, state)]}, end) from the lake's HA switch state history (naive UTC), or
    ({}, None) when there is none. `end` is the last observation, truncated to the hour. Read-only.
    """
    import glob
    import os

    import duckdb

    pattern = os.path.join(lake_dir, "bronze", "ha_state_history", "date=*", "*.parquet")
    if not glob.glob(pattern):
        return {}, None
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT entity_id, last_changed, state FROM read_parquet({sql_str(pattern)}, "
            f"union_by_name=true) WHERE domain = 'switch' ORDER BY entity_id, last_changed"
        ).fetchall()
        end = con.execute(
            f"SELECT MAX(last_changed) FROM read_parquet({sql_str(pattern)}, union_by_name=true)"
        ).fetchall()[0][0]
    finally:
        con.close()
    by_entity = defaultdict(list)
    for entity, at, state in rows:
        by_entity[entity].append((at.replace(tzinfo=None), state))
    return dict(by_entity), end.replace(tzinfo=None, minute=0, second=0, microsecond=0)


def evaluate_lake(lake_dir, zone=None, predictor=REGISTRY[0]):
    """{switch entity: score dict} over the lake's HA switch state history. Read-only."""
    from sa import silver

    by_entity, end = load_switch_history(lake_dir)
    if not by_entity:
        return {}
    zone = zone or silver.TIMEZONE
    own = autonomy_commands(lake_dir)
    return {
        entity: evaluate(hourly_states(trs, end, zone, autonomy=own.get(entity, ())), predictor)
        for entity, trs in sorted(by_entity.items())
    }


def main(argv=None):
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description="Proof predictor scores over the lake (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_lake(args.lake), indent=2, default=str))


if __name__ == "__main__":
    main()
