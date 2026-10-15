"""Read-only shadow-mode review for the LF-4 cutovers (todo/sa/todo_lf4b_baseline_ports.md).

Reads sa_shadow_comparison and prints, per rule, how long the learner and the legacy rule agreed
and differed, every stretch where they differed, and whether the evidence supports a cutover.
Writes nothing. Run it inside a service_sa container (it uses their MySQL environment):

    docker compose exec -T sa-awareness python - < scripts/sa_shadow_review.py
    docker compose exec -T sa-awareness python - --days 14 < scripts/sa_shadow_review.py

The table keeps one row each time a rule's (legacy, learner) pair changes, so a row is the state
from its own time until the next row's (or now, for the last one).
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
from sa import inference_store  # noqa: E402

# Cutover bar from the checklist: a week of shadow, and the rule must have been seen to fire.
MIN_SPAN_DAYS = 7.0
# Learner-only time beyond this share is noise the household would see as extra cards.
MAX_LEARNER_ONLY_SHARE = 0.02
# rhythm_break_anomaly: the learner names every device that is offline when normally on, the legacy
# rule one device, so DIFFER is expected there and judged by hand.
EXPECTED_DIFFER = {"rhythm_break_anomaly"}


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=float, default=0, help="only the last N days (0 = all)")
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
        stretches = []
        for i, (_r, at, _v, legacy, learner, count) in enumerate(rows):
            end = rows[i + 1][1] if i + 1 < len(rows) else now
            state = classify(legacy, count)
            totals[state] += (end - at).total_seconds()
            if state in ("learner only", "legacy only"):
                stretches.append((at, end, state, legacy, learner))
        changes = len(rows)
        print(
            f"== {rule}: {start:%Y-%m-%d %H:%M} -> now ({span / 86400:.1f} days, {changes} changes)"
        )
        for state in ("both quiet", "both fire", "learner only", "legacy only"):
            share = 100.0 * totals[state] / span if span else 0
            print(f"   {state:<13} {fmt_hours(totals[state]):>9}  {share:5.1f}%")
        for at, end, state, legacy, learner in stretches[-10:]:
            print(
                f"   - {state}: {at:%m-%d %H:%M} for {fmt_hours((end - at).total_seconds())}"
                f"  legacy={legacy[:40]}  learner={learner[:90]}"
            )

        problems = []
        if span / 86400 < MIN_SPAN_DAYS:
            problems.append(f"only {span / 86400:.1f} of {MIN_SPAN_DAYS:.0f} days of shadow")
        if totals["both fire"] == 0 and totals["legacy only"] == 0:
            problems.append("legacy never fired, so nothing shows the learner catching it")
        if totals["legacy only"] > 0:
            problems.append(
                f"learner missed the legacy rule for {fmt_hours(totals['legacy only'])}"
            )
        if rule not in EXPECTED_DIFFER and totals["learner only"] > MAX_LEARNER_ONLY_SHARE * span:
            problems.append(
                f"learner fired alone for {fmt_hours(totals['learner only'])} "
                f"(over {MAX_LEARNER_ONLY_SHARE:.0%}): needs a human look"
            )
        if rule in EXPECTED_DIFFER and totals["learner only"]:
            problems.append("learner-only stretches expected here; judge the devices by hand")
        print(
            "   verdict: "
            + ("READY on the data" if not problems else "NOT YET - " + "; ".join(problems))
        )
        print()


main()
