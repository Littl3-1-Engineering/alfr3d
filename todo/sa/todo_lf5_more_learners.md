# LF-5: More L1 learners

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-5

## Status: 🟡 Rate learner (LF-5a, see [todo_lf4b_baseline_ports.md](todo_lf4b_baseline_ports.md)) and drift detector (2026-10-11) deployed. Transition, visitor-arrival cards and the feedback signal are not started.

- [x] **Rate / count** (`learners/rates.py`, nightly; live hourly scoring still open): Poisson or negative-binomial expected rate per dow × hour over gold
      `hourly_rates` (device activity, event rates per stream).
- [ ] **Transition** (SA-12, [todo_transition_learning.md](todo_transition_learning.md)):
      P(B within 10 min of A) over silver `events_clean`, Beta confidence, sample floor. Keep that
      doc's ~2026-11-01 re-check: the blocker is thin organic `device`/presence streams, not code.
- [x] **Drift** (`learners/drift.py`, deployed 2026-10-11, runs last in the nightly `run_learners`):
      two-sided CUSUM (K 0.5, H 5, z clipped at 4) on one daily feature per profiled subject:
      minutes at home per person, daily mean of each scalar series, daily count of each event or
      email stream. Reference = first 14 days of the current regime, median per day type, robust
      sigma with a per-feature floor (45 min; 0.4 on log counts). A change must last 7 days with a
      median z >= 1, and is dated to where its run began. It writes a `drift` profile per subject,
      a `drift` inference for a change in the last 14 days, and **caps `stability`** in the
      profiled learner's row (0.3 at the change, back to 1.0 over 28 days; at most -40 % while an
      alarm builds). 12 tests. On the real lake: 23 subjects watched, 4 recent changes
      (`attention:switch_count` down since 09-16, `email/all` down since 09-24, notification
      messages up since 10-01, track plays down since 09-28), and Athos's presence dated to a
      +4.7 sigma rise on 08-10 and a drop on 08-25, the August move.
      **Open:** device rhythm and household day are not capped (no daily feature yet); the email
      streams change level every few weeks, so their stability is often below 1; the days around the
      HA home change (10-10) are not yet a test case because scalar skips the `describes_ha_home`
      series.
- [ ] **Visitor-arrival prediction cards**: **parked 2026-10-11, nothing to predict yet.** The
      presence outlooks exist, but at the current house only Elenka and Predrag are guest-type
      users with data, and both are near-daily presences (62 and 59 days since July, ~7-10 h a
      visit), so they are routine rather than arrivals; their outlook confidence is 0.2-0.23
      (below the 0.3 card floor) because of the move. Vesna, Gorango and Kuma were last seen in
      April-May, before the move. Revisit when a genuinely occasional visitor shows up; that needs
      an occasional-visitor model (days since last visit, inter-visit gaps), not an hourly P(home).
- [ ] **Card feedback as a learning signal** (SA-1 Phase 3 "earned priority",
      [todo_card_feedback_loop.md](todo_card_feedback_loop.md)): fix the double-counted `shown`
      (web and Deck both report it) before using it.
