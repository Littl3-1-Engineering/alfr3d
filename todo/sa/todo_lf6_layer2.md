# LF-6: Layer-2 inferences (design)

> **Layer:** L2 · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-6

## Status: 🔲 Design only (planned 2026-10-09). Depends on LF-4 and LF-5.

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
