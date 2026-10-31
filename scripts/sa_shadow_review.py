"""Read-only shadow-mode review for the LF-4 cutovers (todo/sa/todo_lf4b_baseline_ports.md).

Reads sa_shadow_comparison and prints, per rule, how long the learner and the legacy rule agreed
and differed, every stretch where they differed, and whether the evidence supports a cutover.
Writes nothing. Run it inside a service_sa container (it uses their MySQL environment):

    docker compose exec -T sa-awareness python - < scripts/sa_shadow_review.py
    docker compose exec -T sa-awareness python - --days 14 < scripts/sa_shadow_review.py

The table keeps one row each time a rule's (legacy, learner) pair changes, so a row is the state
from its own time until the next row's (or now, for the last one).

Agreement percentages say little when the legacy rule is silent by construction (a departure-hour
baseline needs a tight spread, a fixed band ignores the hour), so the verdict is about *episodes*:
contiguous stretches where one side fires. A rule is judged on its flags per week (a flag budget)
and on the episodes only one side saw, which are listed to be adjudicated by hand.
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
from sa import inference_store  # noqa: E402

# Cutover bar: a week of shadow, and the learner's cards must fit a flag budget.
MIN_SPAN_DAYS = 7.0
# Learner episodes per week the household would tolerate as cards.
MAX_LEARNER_EPISODES_PER_WEEK = 4.0
# Cards below this confidence are not shown (the layer-1 card floor), so a learner firing only counts
# as a flag when some subject in it clears the floor.
CARD_CONFIDENCE_FLOOR = 0.3
# Firing separated by less than this is one episode (the pair flips as inputs wobble).
EPISODE_GAP = timedelta(minutes=30)


def fmt_hours(seconds):
    return f"{seconds / 3600:.1f} h"


def classify(legacy, learner_count):
    legacy_fires, learner_fires = legacy != "quiet", learner_count > 0
    if legacy_fires and learner_fires:
        return "both fire"
    if learner_fires:
        return "learner only"
    if legacy_fires:
        return "legacy only"
    return "both quiet"


def confident(text, floor):
    """True if any subject in a learner summary ("<what> conf=0.54 {...}; <what> conf=...") has
    confidence >= floor. Text with no conf= is kept."""
    found = re.findall(r"conf=([0-9.]+)", text or "")
    return not found or any(float(c) >= floor for c in found)


def episodes(rows, now, fires):
    """[(start, end, text)] for the stretches where fires(row) holds, merging gaps under
    EPISODE_GAP. `rows` are (rule, at, verdict, legacy, learner, count) in time order."""
    out = []
    for i, row in enumerate(rows):
        end = rows[i + 1][1] if i + 1 < len(rows) else now
        if not fires(row):
            continue
        text = row[4] if row[5] else row[3]
        if out and row[1] - out[-1][1] < EPISODE_GAP:
            out[-1] = (out[-1][0], end, out[-1][2])
        else:
            out.append((row[1], end, text))
    return out


def overlaps(a, others):
    return any(a[0] < b[1] and b[0] < a[1] for b in others)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=float, default=0, help="only the last N days (0 = all)")
    parser.add_argument("--all", action="store_true", help="list every episode, not the last 12")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=CARD_CONFIDENCE_FLOOR,
        help="ignore learner firing whose subjects are all below this confidence (0 = keep all)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = inference_store.connect()
    cur = conn.cursor()
    sql = (
        "SELECT rule_id, observed_at, verdict, legacy, learner, learner_count "
        "FROM sa_shadow_comparison"
    )
    params = ()
    if args.days:
        sql += " WHERE observed_at >= %s"
        params = (now - timedelta(days=args.days),)
    cur.execute(sql + " ORDER BY rule_id, observed_at", params)
    by_rule = defaultdict(list)
    for row in cur.fetchall():
        by_rule[row[0]].append(row)
    conn.close()

    print(f"Shadow review at {now:%Y-%m-%d %H:%M} UTC\n")
    if not by_rule:
        print("no comparison rows")
        return
    for rule, rows in sorted(by_rule.items()):
        start = rows[0][1]
        span = (now - start).total_seconds()
        totals = defaultdict(float)
        for i, (_r, at, _v, legacy, learner, count) in enumerate(rows):
            end = rows[i + 1][1] if i + 1 < len(rows) else now
            state = classify(legacy, count)
            totals[state] += (end - at).total_seconds()
        changes = len(rows)
        print(
            f"== {rule}: {start:%Y-%m-%d %H:%M} -> now ({span / 86400:.1f} days, {changes} changes)"
        )
        for state in ("both quiet", "both fire", "learner only", "legacy only"):
            share = 100.0 * totals[state] / span if span else 0
            print(f"   {state:<13} {fmt_hours(totals[state]):>9}  {share:5.1f}%")
        learner_eps = episodes(
            rows, now, lambda r: r[5] > 0 and confident(r[4], args.min_confidence)
        )
        legacy_eps = episodes(rows, now, lambda r: r[3] != "quiet")
        learner_only = [e for e in learner_eps if not overlaps(e, legacy_eps)]
        missed = [e for e in legacy_eps if not overlaps(e, learner_eps)]
        weeks = max(span / 604800.0, 1e-9)
        print(
            f"   episodes (learner conf >= {args.min_confidence:g}): "
            f"learner {len(learner_eps)} ({len(learner_eps) / weeks:.1f}/wk), "
            f"legacy {len(legacy_eps)}; only the learner saw {len(learner_only)}, "
            f"only legacy saw {len(missed)}"
        )
        shown = (lambda xs: xs) if args.all else (lambda xs: xs[-12:])
        for label, eps in (("learner only", learner_only), ("legacy only", missed)):
            for at, end, text in shown(eps):
                print(
                    f"   - {label}: {at:%m-%d %H:%M} for {fmt_hours((end - at).total_seconds())}"
                    f"  {text[:110]}"
                )

        problems = []
        if span / 86400 < MIN_SPAN_DAYS:
            problems.append(f"only {span / 86400:.1f} of {MIN_SPAN_DAYS:.0f} days of shadow")
        if len(learner_eps) / weeks > MAX_LEARNER_EPISODES_PER_WEEK:
            problems.append(
                f"{len(learner_eps) / weeks:.1f} learner episodes/week is over the "
                f"{MAX_LEARNER_EPISODES_PER_WEEK:.0f}/week flag budget"
            )
        todo = []
        if learner_only:
            todo.append(f"{len(learner_only)} learner-only episodes")
        if missed:
            todo.append(f"{len(missed)} legacy episodes the learner missed")
        verdict = "WITHIN BUDGET" if not problems else "NOT YET - " + "; ".join(problems)
        if todo:
            verdict += " | adjudicate by hand: " + ", ".join(todo)
        elif not problems:
            verdict += " | no disagreements"
        if not legacy_eps:
            verdict += " | legacy never fired: judge each learner flag on its own"
        print("   verdict: " + verdict)
        print()


main()
