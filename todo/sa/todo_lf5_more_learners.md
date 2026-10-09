# LF-5: More L1 learners

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-5

## Status: 🔲 Not started (planned 2026-10-09). Depends on LF-3.

- [ ] **Rate / count**: Poisson or negative-binomial expected rate per dow × hour over gold
      `hourly_rates` (device activity, event rates per stream).
- [ ] **Transition** (SA-12, [todo_transition_learning.md](todo_transition_learning.md)):
      P(B within 10 min of A) over silver `events_clean`, Beta confidence, sample floor. Keep that
      doc's ~2026-11-01 re-check: the blocker is thin organic `device`/presence streams, not code.
- [ ] **Drift**: Page-Hinkley / CUSUM on gold daily features. Emits `drift` inferences and lowers
      `stability` in every affected profile. Test case: the house move (most HA entities
      `unavailable` from late August).
- [ ] **Visitor-arrival prediction cards** from the presence learner's next-24 h predictions for
      guest-type users.
- [ ] **Card feedback as a learning signal** (SA-1 Phase 3 "earned priority",
      [todo_card_feedback_loop.md](todo_card_feedback_loop.md)): fix the double-counted `shown`
      (web and Deck both report it) before using it.
