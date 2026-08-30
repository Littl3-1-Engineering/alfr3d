# SA-12: Transition learning & anticipation/surprise

## Status: 🔴 Stopped at Phase 0 — SA-11 has not been live long enough to have real transitions
to mine

Last item of the roadmap, Wave 4, explicitly gated on SA-11 (durable household event log)
accumulating real history. The task doc's own Phase 0 instruction is direct: *"Confirm SA-11 has
been live long enough to have real transitions to mine... don't scope this against hypothetical
data."*

## Phase 0 — investigate

Checked directly against this session's real `household_events` data (the same table SA-11
built earlier in this session), not assumed:

- **`household_events` spans barely 10 hours of real history**: earliest row
  `2026-08-29 15:35:40`, latest `2026-08-30 01:56:54` — SA-11 landed *earlier in this same
  session*, so this is genuinely all the runtime it has had, not a stale measurement.
- **Only 71 rows carry the structured `subject_type`/`verb` fields this whole feature depends
  on** (out of 1,217 total rows — most rows are still prose-only from producers SA-11 hasn't
  migrated to structured fields yet). Breakdown: `track/play_start` (57 — the overwhelming
  majority, dominated by whatever was playing during this session's own verification work),
  `user/went_offline` (5), `user/came_online` (5), `calendar_event/created` (2),
  `track/play_stop` (2). No device-to-device transitions, no presence-to-routine transitions —
  none of the task doc's own named candidate pairs (device-to-device, presence-to-device,
  calendar-to-device) have more than a handful of samples, and most have zero.
- Every downstream Phase 0 question the task doc asks (what transition window is empirically
  right, which candidate pairs are worth mining, whether the 6-hourly cadence has headroom for a
  second pass) is unanswerable honestly against 10 hours and 71 structured rows — any number
  picked now would be invented, not derived, which is exactly what this Phase 0 exists to
  prevent.

**Verdict: stop here.** Not a feasibility failure like SA-8, not an environment blocker like
SA-9 — the mechanism this item would build is sound and the task doc's own design (conditional
frequency counts, no ML, the same `entity_baselines`-style sample floor) is well-reasoned. It
simply has no real data to learn from yet. Building `event_transitions`/`compute_transitions()`/
`check_anticipation`/`check_surprise` against 71 rows spanning half a day would produce
confidence values with no statistical meaning, the same anti-pattern (fabricated-looking output
from insufficient data) this entire SA initiative has repeatedly refused to ship.

## Not yet done

- Everything: Phase 1 (`event_transitions` table, `compute_transitions()`), Phase 2
  (`check_anticipation`/`check_surprise`), Phase 3 (decay, explicitly deferred by the task doc
  regardless). None of this should start until SA-11 has accumulated real weeks-to-months of
  structured event history, the same "genuine data runway" precedent SA-2's attention telemetry
  and SA-3's departure baselines both needed before they meant anything.
- **A concrete re-open condition, not just "wait and see"**: revisit once `household_events` has
  (a) enough elapsed real time (weeks, not hours — matching the order of magnitude SA-3/SA-10
  needed for their own day-bucketed baselines) and (b) SA-11 Phase 2's structured `subject_type`/
  `verb` migration has been extended to more producers than the handful populated today (device
  state changes and calendar events barely appear; the candidate pairs this feature needs mostly
  don't exist as structured rows yet, independent of the time-span question).

## Out of scope (per the task doc, unchanged)

- Any regression, neural, or black-box model — moot, nothing was built.
- Cross-household pattern sharing — moot.
- Recency decay (Phase 3) — explicitly deferred by the task doc regardless of this Phase 0
  outcome.
- Any autonomous action on a high-confidence prediction — moot.
