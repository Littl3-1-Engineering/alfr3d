-- Migration 041 (SA-9 Phase 2): entity_baselines gains climate (room) baseline support
--
-- entity_type already has 'room' reserved (migration 033, "gated on SA-9 sensor coverage").
-- Two additions:
-- 1. time_of_day_bucket ('all'/'morning'/'day'/'evening'/'night') -- a new bucketing dimension,
--    not day_bucket (weekday/weekend, added for SA-3 departure baselines): indoor temperature
--    varies by time of day far more than by day of week. Reuses common/timeofday.py's existing
--    coarse_bucket() vocabulary rather than inventing a new one. Every existing row keeps the
--    default 'all', so no existing baseline's identity changes.
-- 2. typical_median_value -- a new generic FLOAT column. The existing median_on_minutes column
--    is duration-shaped (on-time in minutes); a median *reading value* (a temperature, a
--    humidity percentage) doesn't fit that name, so this gets its own column rather than
--    reinterpreting median_on_minutes's literal meaning a second time. typical_daily_min/max
--    are reused as-is for the room baseline's observed value range, same "reuse the existing
--    generic column with a documented per-entity-type meaning" precedent SA-3/SA-10 already set.
ALTER TABLE `entity_baselines`
  ADD COLUMN `time_of_day_bucket` ENUM('all','morning','day','evening','night')
    NOT NULL DEFAULT 'all' AFTER `day_bucket`,
  ADD COLUMN `typical_median_value` FLOAT NULL DEFAULT NULL AFTER `typical_daily_max`,
  DROP INDEX `unique_entity`,
  ADD UNIQUE KEY `unique_entity` (`entity_type`, `entity_id`, `day_bucket`, `time_of_day_bucket`);
