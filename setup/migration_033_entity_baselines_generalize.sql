-- Migration 033 (SA-10): generalise entity_baselines beyond devices/users
--
-- entity_type gains 'room' and 'household' alongside 'device'/'smarthome_device'/'user' (the
-- last added by SA-3, migration 031). 'room' is added as an enum value only -- its computation
-- is gated on SA-9 (ESPHome sensor coverage), which stopped at Phase 0 this session with no real
-- sensor hardware to validate against (see todo/todo_esphome_situational_awareness.md). Adding
-- the enum value now, with no rows ever written for it yet, costs nothing and avoids a second
-- migration purely to add one more enum label later.
--
-- min_sample_count makes "how many samples before this baseline is trusted" an explicit,
-- queryable property of the row itself, rather than a raw constant each check_* method imports
-- and compares against separately (ENTITY_BASELINE_MIN_SAMPLES, DEPARTURE_BASELINE_MIN_SAMPLES,
-- and now HOUSEHOLD_BASELINE_MIN_SAMPLES all differ per entity_type) -- every consumer gets the
-- same "do I trust this yet" answer via `sample_count >= min_sample_count` on the row, not a
-- separate constant lookup per rule.
--
-- typical_last_activity_hour is the one genuinely new column this pass adds (everything else
-- household baselines need reuses an existing column with its original shape intact --
-- typical_active_hour as first-activity hour, typical_daily_min/max as the device-count range --
-- per the task doc's own instruction not to reinterpret median_on_minutes into meaning something
-- different for a household than it means for a device). "Typical occupancy curve" and "typical
-- media hours" need a different storage shape (a distribution, not a scalar) and are
-- deliberately left unimplemented this pass -- see check_household_unusual_day()'s doc comment,
-- same "documented, not forced" precedent check_rhythm_break_anomaly() already set.
ALTER TABLE `entity_baselines`
  MODIFY COLUMN `entity_type` ENUM('device', 'smarthome_device', 'user', 'room', 'household') NOT NULL,
  ADD COLUMN `min_sample_count` INT NOT NULL DEFAULT 0 AFTER `sample_count`,
  ADD COLUMN `typical_last_activity_hour` TINYINT NULL DEFAULT NULL AFTER `typical_active_hour`;
