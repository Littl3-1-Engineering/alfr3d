-- Migration 027: structured subject/verb fields on household_events
--
-- Prose alone can't be queried for "did the kettle event follow the door
-- event." Nullable and additive: a row with no structured fields still
-- logs, still displays -- it just isn't queryable for transitions yet.
-- Producers are migrated to populate these incrementally, in separate
-- commits, starting with device/presence, calendar, music, weather.
ALTER TABLE `household_events`
  ADD COLUMN `subject_type` VARCHAR(32) NULL DEFAULT NULL AFTER `message`,
  ADD COLUMN `subject_id` VARCHAR(64) NULL DEFAULT NULL AFTER `subject_type`,
  ADD COLUMN `verb` VARCHAR(32) NULL DEFAULT NULL AFTER `subject_id`;
