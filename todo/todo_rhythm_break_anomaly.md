# Deck: Rhythm-Break Anomaly Cards

## Status: ✅ Built 2026-08-28 (not yet on-device/live verified; no real baseline data yet)

Backend: migration `0025_entity_baselines.py` (+ `migration_023_entity_baselines.sql`) creates
`entity_baselines`. `compute_entity_baselines()` (module-level, scheduled every 6h alongside
`rebuild_music_recommendations`) reconstructs on/off sessions from `device_history` in Python
(median/typical-hour/min/max via `statistics`), skipping entities under
`ENTITY_BASELINE_MIN_SAMPLES` (5). `MyDaemon.check_rhythm_break_anomaly()` compares online
devices against their baseline via a single `TIMESTAMPDIFF`-based SQL query, firing only past
`typical_daily_max + RHYTHM_BREAK_GRACE_MINUTES` (15). Only the "still on past typical" deviation
is implemented -- "unusual hour" / "expected absent" remain scoped, not built (see Design below).
6 new tests (`TestCheckRhythmBreakAnomaly`, `TestComputeEntityBaselines`). Deck:
`RhythmBreakAnomalyInsight` + `rhythm_break_anomaly` `ContextRule` (TimeSensitive tier, priority
9, near `focus_needed_heads_up`), verbatim-content display (no fixed shape to parse). Compiles
clean, ktlint/detekt clean.

**Real-world caveat**: `compute_entity_baselines()` has never run against production data --
until it's run for `ENTITY_BASELINE_LOOKBACK_DAYS` (30 days) against real `device_history`, no
device will have enough sessions to clear `ENTITY_BASELINE_MIN_SAMPLES` and no anomaly card can
fire yet. This is expected, not a bug.

---

## Status: 🔲 Not started (historical, see above)

## Overview

Build a per-entity baseline (median on-time, typical active hour, typical daily range) from
existing IoT device-state history, and fire a Deck card only on deviation from that baseline —
garage open N minutes past its usual max, a light on at an unusual hour, an expected device never
coming online. Scoped in Notion 2026-08-28. Called out there as the highest-value of the five new
Deck data features, because it's the only one that surfaces a genuine surprise rather than
restating current state — and it needs no new external data source, just aggregation over data
the existing 15-minute IoT sync already ingests into `device_history`/`device_command_history`.

## Design

### Schema
New table `entity_baselines` (migration `setup/migrations/versions/0025_entity_baselines.py`,
companion SQL under `setup/`, following the `0023_refresh_tokens.py` /
`migration_022_refresh_tokens.sql` create-table-migration pattern):

```sql
CREATE TABLE entity_baselines (
  id INTEGER UNIQUE AUTO_INCREMENT,
  entity_type ENUM('device','smarthome_device') NOT NULL,
  entity_id INTEGER NOT NULL,
  median_on_minutes FLOAT NULL,
  typical_active_hour TINYINT NULL,
  typical_daily_min FLOAT NULL,
  typical_daily_max FLOAT NULL,
  sample_count INTEGER NOT NULL DEFAULT 0,
  computed_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_entity (entity_type, entity_id)
);
```

### Baseline computation job
- New module-level `compute_entity_baselines()` in `alfr3ddaemon.py`, registered with the
  existing `schedule` library alongside the other periodic jobs (~line 924-930):
  `schedule.every(6).hours.do(compute_entity_baselines)` — same cadence as
  `rebuild_music_recommendations()`, since both are "recompute a derived model from history"
  jobs, not real-time.
- Queries `device_history` (and `device_command_history` for smarthome devices) grouped by
  entity, computing median on-duration, most common active hour-of-day, and daily min/max active
  window over the available history.
- Entities under a minimum sample-count threshold are skipped (not upserted) rather than given a
  noisy baseline from too little data — avoids false-positive anomalies in the first weeks after
  this ships.

### Anomaly check
- New `MyDaemon.check_rhythm_break_anomaly()` DISPLAY_RULES method: for each currently-online (or
  recently-transitioned) entity with a baseline row, compare current on-duration/hour against
  `typical_daily_max`/`typical_active_hour`. Fires a card only past a deviation threshold (exact
  threshold to be tuned once real baseline data exists — start conservative to avoid noise).
  Priority `2.6` (actionable, near `event`/`gathering` tier, per the "genuine surprise" framing).
  Card shape: `{"mode": "rhythm_break_anomaly", "content": str, "priority": 2.6, "entity_name":
  str, "deviation_type": "still_on_past_typical" | "unusual_hour" | "expected_absent"}`.
- Register in `DISPLAY_RULES`.

### Deck
- `alfr3d_deck`: new insight type for `mode == "rhythm_break_anomaly"` in
  `contextawareness/SituationalInsights.kt`, registered in `ContextRules.kt`'s
  `DEDICATED_SITUATIONAL_MODES`, dedicated "anomaly" icon (e.g. warning-amber style, distinct
  from the household-composition urgent icon so the two alert types read differently).

## Open questions (tune after real data exists)

- Exact deviation threshold (how far past `typical_daily_max` before it's a card, not noise).
- Whether `entity_baselines` needs periodic pruning/decay so an entity's baseline adapts to a
  genuinely new routine rather than treating the new routine as permanent anomaly.

## Related

- `todo_iot.md`, `todo_iot_central_control.md` — own the `device_history`/
  `device_command_history` ingestion this feature reads from.
