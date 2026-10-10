# LF-3: Inference contract + presence learner (first proof)

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-3

## Status: 🟢 Deployed to the production NUC 2026-10-10 (migration 046 / alembic 0051). 9 profiles and 9 outlooks are stored and the running awareness loop has loaded them. The first *scheduled* fit (03:30 UTC) is unconfirmed at the time of writing; the same function was run by hand.

New: `sa/confidence.py`, `sa/inference_store.py`, `sa/learners/{base,presence}.py`,
`SAEngine.check_presence_deviation`, `context_frame.fetch_person_presence`, and a nightly
`learner.run_learners()` after the silver/gold rebuild.

## The question it must answer

2026-10-09 (Friday): Athos is normally home 9-17 on weekdays and was out all day. Nothing fired.
This learner exists so that does, with a stated probability and confidence, and so that a
normal weekday does not.

## Scope

- [x] Migration 046 / alembic 0051: `sa_profiles` and `sa_inferences` (schema in
      [SA_ROADMAP.md](SA_ROADMAP.md#inference-contract-sa_inferences)), 730-day retention EVENT on
      `sa_inferences`, and `sa_inferences` added to the storage metrics. Backup
      `alfr3d_backup_20261009_221958_pre_0051.sql.gz`, rehearsed on a restored copy (up, down, up).
- [x] `Learner` base class (`fit` runs in `sa-learner`, `score` in `sa-awareness`), plain
      `Profile`/`Inference` records, and the confidence function in one place
      (`sa/confidence.py`).
- [x] **Presence profile**, per **user** of every type (residents and visitors): recency-weighted
      Beta-Binomial over gold `presence_grid`, pooled dow-hour -> weekday/offday-hour -> overall,
      Ontario holidays treated as offdays. Deviation (probability, surprise in bits, confidence)
      and a 24 h outlook per person.
- [x] `sa-awareness` scores each person's current state (`user.state`, logged from the phone)
      every cycle against the in-memory profile and persists deviations.
- [x] `check_presence_deviation(frame)`: an ambient card for an owner/resident who is away,
      suppressed by a covering calendar event. Priority 2.75, one card per person.
- [~] Kafka `sa-profiles-updated` and `sa-inferences` topics: **not built, on purpose.**
      Awareness polls `MAX(computed_at)` once per cycle instead (no new topic, no consumer thread,
      can't miss a message across a restart), and nothing consumes an inference stream yet.

## What the real data changed

- **The constants were measured, not planned.** Scored by walk-forward log-loss on two disjoint
  windows (Aug 17-Sep 13, Sep 14-Oct 9) for the three residents, a **3-week half-life** beat the
  planned 8 weeks (0.404 vs 0.425), a **stronger day-of-week prior (8)** beat a weak one, and a
  **weak daytype prior (2)** was best. The gain is modest and the optimum sat at the edge of the
  grid, so these are "measured and good enough".
- **Confidence clusters low.** It is a product of four terms, so over the backtest its median was
  0.31-0.35 and its maximum ~0.5 for each resident. A threshold on it has to be calibrated:
  `MIN_CARD_CONFIDENCE = 0.3` gives each resident roughly one card-day every one to two weeks
  (0.65/week at 3.0 bits), and the days it picks for Athos are the real absences (09-18, 09-26,
  10-07, 10-08, 10-09). Surprise does most of the discriminating; the confidence gate mostly
  screens out thin-history cases.
- **A short absence is not evidence.** Phones nap ~30 minutes without anyone leaving, so a
  deviation needs the person gone `MIN_AWAY_MINUTES = 60`.
- **`signal` is a reserved word in MySQL** (the `SIGNAL` statement). The migration quoted it but
  my inserts did not, and the mocked store tests could not catch it; a run against a scratch
  MySQL did. Every statement now quotes it and a test pins that.

## Verify

Walk-forward on the production lake, each day's model fitted only on data before that day,
evaluated at 11:30 local:

| Day | P(home) | Observed | Verdict |
|---|---|---|---|
| **Fri 10-09 (the case)** | 0.90 | away 176 min | **deviation, 3.35 bits, P(observed) 0.098, confidence 0.386 -> card** |
| Fri 10-02 / 09-25 / 09-18 | 0.92-0.97 | home | none |
| Thu 10-08 | 0.96 | away 150 min | deviation, 4.75 bits, confidence 0.376 -> card |
| Mon-Wed 10-05..07 | 0.95-0.96 | home | none |

- [x] The absent Friday is flagged and normal weekdays are not (above, and
      `TestReplay` on a synthetic lake).
- [x] 59 tests in `tests/test_sa_presence.py`: maths, scoring gates, store, the rule, reload.
- [x] The store's SQL run against a scratch MySQL restored from a backup with the real lake: JSON
      round-trips through MySQL score identically, a persisting absence is one row updated in
      place, outlooks are replaced and not accumulated, pruning works.
- [x] Deployed; the live loop loaded the 9 profiles at 03:01:18 right after the fit and ran the
      rule cleanly. No card now, correctly: everyone expected home is home.
- [x] **Outlooks vs. reality** (mean P(home) over the next 24 h vs. share of the last 7 days
      actually home): Elenka 0.82/0.88, Jenna 0.75/0.75, athos 0.74/0.80, Munja 0.79/0.69,
      Predrag 0.39/0.32, and 0.00/0.00 for guests not seen for months. Guest confidence is
      deliberately low (0.14-0.16): their phones are sighted sparsely (`source_quality` 0.3).
- [ ] **Not demonstrated live:** the 10-09 absence happened before this rule was running, so
      there is no `sa_inferences` row for it in production, and no real card has fired yet.
      The proof is the walk-forward replay and the tests, not a stored row.
- [ ] Not yet observed: the scheduled nightly fit.

## Known limits / follow-ups

- **Occasional visitors are invisible to this model.** With a 3-week memory, someone who visited
  on a few Saturdays months ago decays to P(home) ~ 0.00 (Vesna, Gorango, Kuma). It answers "who
  is around now", not "who is likely to arrive". Anticipating arrivals needs a different shape:
  visit frequency and typical days over a long horizon. That is the LF-5 visitor-arrival learner.
- **No drift learner yet.** The weekday series is falling (1.00, 0.77, 0.74, 0.48, 0.32 over the
  last five weekdays). `stability` only compares two fortnights; LF-5's change-point detection
  should say "this is a new pattern" explicitly.
- A resident who left (Vanja, last seen 09-03) keeps a profile that has learned "away"; she raises
  nothing, which is right, but she is not marked as gone.
- Replay's "home" uses a 31-minute lag after the last sighting to mimic `user.state`; the live
  value comes from the household's own state logic, whose exact timing I did not read.
- The card text names the weekday and hour only; it does not say how long the person has been out
  beyond the `because` list.
- `n_eff` on a profile is the total recency weight across all 168 cells, not a per-cell figure.
