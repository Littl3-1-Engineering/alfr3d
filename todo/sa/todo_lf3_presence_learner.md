# LF-3: Inference contract + presence learner (first proof)

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-3

## Status: 🔲 Not started (planned 2026-10-09). Depends on LF-2.

## The question it must answer

2026-10-09 (Friday): Athos is normally home 9-17 on weekdays and was out all day. Nothing fired.
This learner exists so that does, with a stated probability and confidence, and so that a
normal weekday does not.

## Scope

- [ ] Migration: `sa_inferences` and `sa_profiles` (schema in
      [SA_ROADMAP.md](SA_ROADMAP.md#inference-contract-sa_inferences)), with a retention EVENT on
      `sa_inferences`.
- [ ] `Learner` base class in `service_sa`: `fit(gold) → profiles` (runs in `sa-learner`),
      `score(now, state) → inferences` (runs in `sa-awareness`). Shared confidence function.
- [ ] **Presence profile**, per **user** of every type (residents and visitors):
  - P(home) per dow × hour as a Beta-Binomial over gold `presence_grid`, time-decayed with an
    8-week half-life.
  - Partial pooling dow → weekday/weekend → all days, so sparse cells (visitors) borrow strength.
  - Deviation: current state vs. P(home) for this cell, as probability and surprise.
  - Prediction: next-24 h P(home) per user, which is visitor anticipation.
  - Confidence: posterior width (sufficiency), presence coverage for the user today, source
    quality from silver, stability (drops after a detected regime change).
- [ ] `sa-awareness` scores live as presence events arrive, against the in-memory profile, and
      persists/publishes inferences.
- [ ] New rule `check_presence_deviation(frame)`, gated on probability and confidence thresholds,
      suppressed when a calendar event covers the time (as SA-3 does). Tone: ambient observation,
      e.g. "Out today, usually home on Fridays", never a welfare check.

## Verify

- Unit tests for Beta pooling, decay and each confidence term.
- After backfill on the NUC: 2026-10-09 scores a `presence.home` deviation for Athos during 9-17,
  shown with a `SELECT` from `sa_inferences` including probability and confidence; a normal
  weekday does not.
- Visitor predictions sanity-checked against known recent visits.
