-- Migration 031 (SA-3): per-user departure baselines -- entity_baselines gains 'user'
--
-- Extends the entity_baselines pattern (migration 023) rather than a parallel table, per the
-- SA-3 task doc. Two additions:
-- 1. entity_type ENUM gains 'user' alongside the existing 'device'/'smarthome_device'.
-- 2. A new day_bucket column ('all'/'weekday'/'weekend') joins the unique key.
--    entity_baselines had no day-of-week dimension before this (one row per entity, a single
--    full-window aggregate) -- user departure baselines must keep weekday and weekend separate
--    (a Saturday lie-in is not an anomaly), so day_bucket exists specifically for entity_type =
--    'user'. Existing device/smarthome_device rows get day_bucket = 'all', preserving their
--    existing one-row-per-entity behavior unchanged.
--
-- No new numeric columns: 'user' rows reuse the existing generic FLOAT/TINYINT columns with a
-- different meaning (documented in compute_entity_baselines()) --
-- typical_active_hour = typical first-departure hour, typical_daily_min/typical_daily_max =
-- earliest/latest observed departure hour in the sample (the "spread" the task doc asks for),
-- median_on_minutes stays NULL (on-duration doesn't apply to a departure-hour baseline).

ALTER TABLE `entity_baselines`
  MODIFY COLUMN `entity_type` ENUM('device', 'smarthome_device', 'user') NOT NULL,
  ADD COLUMN `day_bucket` ENUM('all', 'weekday', 'weekend') NOT NULL DEFAULT 'all' AFTER `entity_id`,
  DROP INDEX `unique_entity`,
  ADD UNIQUE KEY `unique_entity` (`entity_type`, `entity_id`, `day_bucket`);
