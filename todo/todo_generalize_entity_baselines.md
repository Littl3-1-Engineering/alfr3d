# SA-10: Generalise entity_baselines to users, rooms & household

## Status: 🟢 Built and live-verified 2026-08-30 (a real MySQL `ONLY_FULL_GROUP_BY` bug caught
and fixed live); deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; `service-daemon`
rebuilt and redeployed; verified live with a clean cycle and a real authenticated API response.
The 175s device-baseline timing this design was built around was itself measured on this same
box, so the real production `compute_entity_baselines()` run there is now the same code this
doc's Phase 0 timed -- worth a real before/after comparison next time it's convenient to check.

Last item of Wave 3, following SA-6 (in progress) and the two Phase-0-stopped items SA-9/SA-8.
Widens `entity_baselines` (the mechanism SA-3 already extended to `'user'`) to also cover
`'room'` (enum value only, gated on SA-9) and `'household'` (fully computed).

## Phase 0 — investigate

- Read `compute_entity_baselines()` and confirmed which existing columns genuinely transfer to a
  household subject with their *original* shape intact, per the task's own explicit instruction
  not to reinterpret a column to mean something different per entity type:
  `typical_active_hour` → typical first-activity hour (same "a representative hour of day"
  shape SA-3's departure hour already established as acceptable reuse); `typical_daily_min`/`max`
  → device-count range (a literal, unforced fit — these columns were already "min/max" in
  concept). `median_on_minutes` has no honest household equivalent and stays NULL for these rows
  rather than being stretched to mean something new, per the task's explicit warning against
  exactly that. One genuinely new column was added, `typical_last_activity_hour` — "typical
  occupancy curve" and "typical media hours" (SA-2 telemetry) need a distribution, not a scalar,
  and are deliberately left unimplemented and documented, the same "documented, not forced"
  precedent `check_rhythm_break_anomaly()` already set for its own unbuilt branches.
- **Confirmed SA-3's `'user'` modelling and followed it rather than diverging**, per the task's
  own instruction: weekday/weekend `day_bucket` (not per-specific-weekday), reused generic
  columns, a sample-count floor gate.
- **Measured real runtime headroom on the actual production hardware, not estimated it.**
  Timed the *existing, pre-SA-10* device-only `compute_entity_baselines()` directly on
  `alfr3d@192.168.2.200` (the real NUC, same box SA-6/SA-8 used): **175.4 seconds** for the
  per-device Python session-reconstruction loop alone, on real ~1.48M-row `device_history` data.
  A genuinely significant pre-existing cost (not something this task introduced), confirming the
  task's own concern that "adding subject types multiplies the work" is worth taking seriously —
  which shaped Phase 1's design decision below.
- **Decision this shaped**: compute the new `'household'` baseline as a single SQL `GROUP BY`
  aggregate, not a repeat of the expensive per-device Python loop pattern. Verified this
  empirically, not just architecturally (see Live verification): the household block added
  **~1.1 seconds** to the local dev stack's total runtime, not a multiple of it.
- Added `min_sample_count` as an explicit, queryable column (not a raw constant scattered across
  `check_*` methods) — every consumer's "do I trust this baseline yet" check is now
  `sample_count >= min_sample_count` read off the row itself, the same pattern for all three
  computed entity types.

## Phase 1 — widen the mechanism

Migration 0035 (raw SQL `migration_033_entity_baselines_generalize.sql`): `entity_type` gains
`'room'` and `'household'`; new `min_sample_count` and `typical_last_activity_hour` columns.
`'room'` is enum-only this pass — its computation is gated on SA-9's live sensor validation,
which stopped at Phase 0 this session (no real or virtual ESPHome node reachable, see
`todo/todo_esphome_situational_awareness.md`).

## Phase 2 — household-level baselines

`compute_entity_baselines()` extended with a household block: a single derived-table `GROUP BY`
query over `device_history` (all devices, not just claimed ones — household-level "is the house
awake" is a broader question than SA-3's per-resident signal), bucketed weekday/weekend, giving
typical first/last-activity hour and device-count range per bucket. `HOUSEHOLD_BASELINE_MIN_SAMPLES`
(14) and `HOUSEHOLD_BASELINE_LOOKBACK_DAYS` (=`DEPARTURE_BASELINE_LOOKBACK_DAYS`, 120) reuse
SA-3's established reasoning rather than re-deriving new numbers for a conceptually similar
question.

## Phase 3 — one household rule, plus the two deferred rhythm_break_anomaly branches

`check_household_unusual_day()`: fires only late enough in the day that "today" has had a real
chance to look normal (past the bucket's own `typical_last_activity_hour` — this alone makes it
structurally impossible to fire twice in one day), and only on a **strong, multi-signal**
deviation — both the device-count range and the first-activity hour must be off, not just one.
Priority 6.5, just below `household_composition`'s ambient variant (6.2). Tone matches SA-3's
own constraint exactly: an observation ("{day} is running differently than usual"), never a
concern.

`check_rhythm_break_anomaly()` gained its two previously-scoped-but-unbuilt branches,
`unusual_hour` (a currently-online device's current hour is far from its `typical_active_hour`,
circular distance so midnight wraparound doesn't false-positive) and `expected_absent` (an
offline device with a reliable baseline is still absent within a window after its
`typical_active_hour` — known limitation: doesn't handle a `typical_active_hour` that itself
wraps past midnight, documented rather than silently wrong). Checked in order
(`still_on_past_typical` → `unusual_hour` → `expected_absent`), first match wins, same "one card
per cycle" shape as before.

## Testing

`TestComputeHouseholdBaselines` (3 tests): upserts both buckets correctly from real-shaped
aggregate rows; skips a bucket below the sample floor; confirms the household block is genuinely
one query, not a per-entity loop, regardless of history size. `TestCheckHouseholdUnusualDay` (8
tests): fires on a genuine dual-signal deviation once the day is "over"; no baseline; below the
sample floor; too early in the day (and never even reaches the second query); single-signal
deviations on either axis alone correctly don't fire; no DB call at all without
`frame.local_dt`/`day_mood`; DB error handling. `TestCheckRhythmBreakAnomaly` gained 4 tests for
`unusual_hour`/`expected_absent` (including confirming each later query is only reached once
every earlier one comes back empty) and the empty/DB-error paths. Two pre-existing
`TestComputeEntityBaselines` tests and all `TestComputeUserDepartureBaselines`/
`TestComputeHouseholdBaselines` tests updated for the new `min_sample_count` column and the
household block's extra `fetchall()` call. `TestDecideDisplays`/`TestCardSuppression`'s
"everything fires" end-to-end tests and exact mode-order list updated for the 19th registered
rule. Full suite: **458 passed, 9 skipped** (MySQL-integration skips, unrelated), lint clean.

## Live verification (2026-08-30, real docker-compose stack)

- Migration 0035 applied cleanly (alongside SA-6's pending 0034); confirmed via `DESCRIBE` that
  `entity_type` gained `'room'`/`'household'` and both new columns landed as designed.
- **First redeploy caught a real bug**: `Entity baseline computation error: (1055, "Expression
  #1 of SELECT list is not in GROUP BY clause and contains nonaggregated column
  'device_history.timestamp' which is not functionally dependent on columns in GROUP BY clause;
  this is incompatible with sql_mode=only_full_group_by")`. The original query grouped by an
  inline expression (`DATE(timestamp + INTERVAL %s SECOND)`) while also referencing raw
  `timestamp` again in the SELECT list (wrapped in `DAYOFWEEK(DATE(...))`) — MySQL's
  `ONLY_FULL_GROUP_BY` mode (the production default) can't always prove functional dependency
  through nested function calls the way it can for a bare column. A purely mocked unit test
  couldn't have caught this — the mocks don't run real SQL. Fixed by restructuring as a derived
  table: compute `local_date`/`first_ts`/`last_ts`/`device_count` once in an inner `GROUP BY
  local_date` query, then reference those column names (not raw `timestamp`) in the outer
  SELECT. Verified the fix directly against the real database afterward.
- **Real runtime measured, before and after, on this session's dev stack** (same real ~1.48M-row
  `device_history` dataset as the production NUC): pre-SA-10 baseline (device + SA-3 user blocks
  only) **37.98s**; full run including the new household block **39.08s** — **~1.1 seconds**
  added for an entirely new baseline subject type, confirming the single-aggregate-query design
  choice (motivated by the NUC's 175s device-loop timing) actually paid off rather than just
  sounding good in the design doc.
- Real household baseline row landed: weekday bucket, `typical_active_hour=0`,
  `typical_last_activity_hour=23`, device-count range `18-63`, `sample_count=18` (clears the
  `min_sample_count=14` floor); weekend bucket correctly absent (8 samples, below the floor) —
  matches the household's own genuinely near-continuous device activity pattern, not a bug.
  `check_household_unusual_day()` ran cleanly every cycle with no errors, correctly silent
  (gated on `typical_last_activity_hour=23`, not yet reached during this verification window).
- **A real `unusual_hour` firing was observed live** through the actual JWT-authenticated
  `GET /api/situational-awareness` read path (not just the daemon's own logs): `{"mode":
  "rhythm_break_anomaly", "content": "Pixel-6a is on at an unusual hour", "deviation_type":
  "unusual_hour", "data": {"current_hour": 1, "typical_active_hour": 14, "because": ["on at
  01:00, typically active around 14:00"]}}` — a real device, a real deviation, valid JSON
  end-to-end.

## Not yet done

- **No live `expected_absent` or `household_unusual_day` firing observed** — the former needs a
  device with a reliable baseline to genuinely miss its usual online window during this
  verification session (didn't happen to occur); the latter needs `typical_last_activity_hour`
  (23:00 for this household) to actually pass locally, which this session's verification window
  didn't reach. Both are covered by direct unit tests; a real end-to-end firing for each remains
  open, same category of gap as several other SA items this session (SA-4's `empty_house_still_on`,
  SA-3's `athos`-weekend baseline).
- `'room'` baselines remain enum-only, correctly gated on SA-9 (stopped at Phase 0).
- "Typical occupancy curve" and "typical media hours" (SA-2 telemetry) remain unimplemented,
  documented rather than forced into a column shape that doesn't fit them.
- The `expected_absent` branch's known midnight-wraparound limitation (a `typical_active_hour`
  very late at night won't be checked correctly) — documented, not fixed, narrow edge case.

## Out of scope (per the task doc, unchanged)

- Any ML model — medians, ranges, and counts only, the same vocabulary already in use.
- Room baselines beyond the enum value (gated on SA-9).
- Predictive action — this layer describes what's unusual; it doesn't decide what to do about it.
