-- Migration 009: Routine Triggers & Conditions (WHEN / IF / THEN)
-- Adds event-based triggers (sunrise, sunset, person arrival, device on/off)
-- and IF conditions (person home, device state, temperature, mode).

-- Event triggers: JSON array of {type, params} evaluated in addition to the
-- time column. Supported types:
--   sunrise / sunset                        (params: {})
--   person_arrives / person_leaves          (params: {user_id})
--   device_turns_on / device_turns_off      (params: {device_id})
-- Multiple triggers are OR-combined; a routine fires when ANY match.
ALTER TABLE `routines` ADD COLUMN `triggers` JSON NULL AFTER `actions`;

-- IF conditions: JSON array of {type, params}, ALL must evaluate true.
-- Supported types:
--   person_is_home       (params: {user_id})
--   person_is_away       (params: {user_id})
--   anyone_home / no_one_home   (params: {})
--   device_is_on / device_is_off  (params: {device_id})
--   temperature_above / temperature_below  (params: {value})
--   mode                 (params: {mode: day|night|home|away})
ALTER TABLE `routines` ADD COLUMN `conditions` JSON NULL AFTER `triggers`;
