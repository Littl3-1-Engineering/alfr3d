# LF-6: Layer-2 inferences (design)

> **Layer:** L2 · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-6

## Status: 🟡 Design settled 2026-10-11 (below); `away_unusual` built and live in shadow (2026-10-11). One L2 inference already exists: `household_unusual_day` (`learners/household_day.py`).

Layer 2 consumes L1 inferences, never raw data. Its inputs are rows in `sa_inferences` with
`layer = 1`. Its outputs are rows with `layer = 2` whose `evidence` lists the parent inference ids.

## Questions this doc must settle

- **Combination method.** Default: confidence-weighted Fisher's method over L1 tail probabilities
  for "is this unusual"; noisy-OR for "is X happening" from several weak signals. When is a small
  Bayesian network worth it instead?
- **Confidence propagation.** An L2 inference's confidence can't exceed what its inputs support.
  Proposal: the weighted mean of parent confidences, times an agreement term.
- **Double counting.** Two L1 inferences built on the same silver source (e.g. presence and
  departure time both from arp-scan) are not independent evidence.

## Candidates

- `household_unusual_day`: rebuilt from SA-10's two-signal rule
  ([todo_generalize_entity_baselines.md](todo_generalize_entity_baselines.md)).
- "Day off": presence deviation + empty calendar + morning routine skipped.
- "Away trip": multi-day absence across residents + geofence far from home.
- "Gathering likely tonight": visitor arrival predictions + calendar + past gathering patterns.

## What L1 offers today (production, 2026-10-11)

`sa_inferences`, layer 1: `device_rhythm` deviations (46, conf ~0.46), `scalar_baseline` (60, ~0.74),
`event_rate` (3, ~0.72), `presence_profile` deviations (6, ~0.23) and predictions (9), `drift` (4,
~0.71). Layer 2: only the household-day learner, which scores live and writes nothing on a quiet
day. Presence confidence is low (0.2-0.4) because the history is short; L2 must not hide that.

## Settled design

- **Combination.** Fisher over tail probabilities for "is this unusual", as household-day does. Each
  parent's weight is its confidence, so a 0.23-confidence presence deviation cannot carry a result
  alone. Noisy-OR only for "X is happening" built from independent weak signals (gathering). No
  Bayesian network until two L2 rules need shared hidden state.
- **Confidence.** `min(weighted mean of parent confidences, 1 - max parent stability penalty)`,
  where the stability penalty is the drift cap already written on L1 rows. After a regime change an
  L2 inference inherits the lower number for free.
- **Double counting.** Each L1 inference declares a `source_family` in its evidence (`presence`:
  arp/wifi, `ha`, `calendar`, `attention`, `email`, `weather`). Parents from the same family count
  once (the most surprising), so presence plus device rhythm of the same phone is one vote.
- **Contract.** `layer=2`, `evidence.parents` = parent inference ids, `evidence.families` = families
  that voted. Window = the union of parent windows. Upserted like L1 rows. Never reads bronze/silver.
- **Where it runs.** A shadow-style pass after the L1 pass in `sa-awareness` (hourly or on a new
  L1 row), not in `sa-learner`, because inputs are live L1 rows. Cards come later and only through
  the existing card gates.

## First build: `away_unusual`

Prompted by 2026-10-09 (Athos out on a weekday). Inputs: presence deviation (someone usually home is
away), device rhythm (their phone's expected-absent), attention/calendar family when present
(empty calendar makes "out" less surprising for a day off). Output: one L2 row per person, so the
card can say who and why. Success test: replay 10-09 and see it fire at >= 3 bits with the parents
listed, and see it stay quiet on the normal weekdays since 08-15. Built as a pure function over
parent rows so the replay needs no DB.

## Later candidates

"Day off" (presence + empty calendar + skipped morning routine), "away trip" (multi-day, residents,
geofence far), "gathering likely tonight" (visitor predictions + calendar + history).

## Built: `away_unusual` (2026-10-11)

`learners/away_unusual.py`: pure `combine()` over L1 rows, `ShadowRunner.away()` scores each person
who is out against their presence profile, adds the deviations of devices they own, persists the
layer-2 row to `sa_inferences` and logs `LIVE away_unusual:` when the set of people changes. Never
a card. Rules as designed, plus one correction found by testing: a weakly trusted extra family
could dilute the confidence-weighted Fisher p above the best single family, so the result is capped
at the best family's p (more evidence never lowers surprise). Corroboration (owned devices offline
over owned devices with a rhythm profile) scales confidence from 0.6x to 1.0x, not probability.

Replay on the lake (presence only, walk-forward), 08-15 to 10-11: Athos 10-09 fires 11:30-13:30 at
3.3-4.4 bits, conf 0.39 (it is quiet before 11:00 because he is not yet 60 minutes away). Over the
whole period 23 person-days flag across the four residents (about 10 %), 4.8 bits at most, which is
the presence learner's own rate: **today it adds no selectivity over L1.** What it adds is the
structure (parents, families, corroboration) and the slot for the first genuinely independent
family (calendar free/busy, HA trackers). Live: Elenka and Jenna flagged 6 bits at midnight.

Next: an independent family (calendar busy from `calendar_busy`: a booked absence should lower the
surprise, not just gate the card), then "day off" and "away trip".
