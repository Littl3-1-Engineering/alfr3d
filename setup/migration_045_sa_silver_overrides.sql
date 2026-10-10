-- Migration 045 (2026-10-10): hand-editable inputs to the SA silver layer (LF-2,
-- todo/sa/todo_lf2_silver_gold.md).
--
-- Silver cleans bronze once so no rule or learner has to. Two kinds of cleaning can't be derived
-- from the data and need a human decision, so they live in small tables anyone can fix with a
-- plain INSERT/UPDATE, no deploy: the next nightly silver build picks them up.
--
--  sa_data_exclusions : time windows of rows to drop from silver (test/verification bursts).
--  sa_sensor_aliases  : which stable sensor a retired smarthome_devices id belonged to. A sensor
--                       that power-cycles comes back under new ids (SA-9, 2026-09-27) and the old
--                       ids exist in no snapshot, so their identity can't be recovered from data.
--
-- All timestamps are UTC, like the tables they filter.

CREATE TABLE IF NOT EXISTS `sa_data_exclusions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `source` VARCHAR(64) NOT NULL,              -- bronze table the rows come from, e.g. household_events
  `event_type` VARCHAR(32) NULL,              -- optional narrowing (household_events.event_type)
  `subject_id` VARCHAR(64) NULL,              -- optional narrowing (household_events.subject_id)
  `start_ts` DATETIME NOT NULL,
  `end_ts` DATETIME NOT NULL,
  `reason` VARCHAR(255) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sa_data_exclusions_window` (`source`, `event_type`, `subject_id`, `start_ts`, `end_ts`)
);

CREATE TABLE IF NOT EXISTS `sa_sensor_aliases` (
  `smarthome_device_id` INT NOT NULL,         -- a retired (or current) smarthome_devices.id
  `sensor_key` VARCHAR(160) NOT NULL,         -- stable identity: "<node hostname>:<sensor name>"
  `evidence` VARCHAR(255) NOT NULL,           -- how the mapping was established
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`smarthome_device_id`)
);

-- Seed: the iot test bursts the todos already name (todo_next_session 2026-09-16 interim SA-12
-- check; todo_transition_learning "bursts 2026-09-16/17, 10-01/02"). Windows are the minutes the
-- lake shows >= 4 iot events; only iot events are dropped, never other event types.
INSERT IGNORE INTO `sa_data_exclusions` (`source`, `event_type`, `subject_id`, `start_ts`, `end_ts`, `reason`) VALUES
  ('household_events', 'iot', NULL, '2026-09-16 03:02:00', '2026-09-16 03:05:00', 'scripted test burst: 13 device events in 2 minutes (todo_next_session 2026-09-16)'),
  ('household_events', 'iot', NULL, '2026-09-17 01:15:00', '2026-09-17 01:19:00', 'test burst: 22 volume-set events on one media player (todo_transition_learning)'),
  ('household_events', 'iot', NULL, '2026-10-01 11:56:00', '2026-10-01 11:59:00', 'test burst: 6 device events in one minute (todo_transition_learning 10-01/02)'),
  ('household_events', 'iot', NULL, '2026-10-01 14:11:00', '2026-10-01 14:14:00', 'test burst: 4 device events in one minute (todo_transition_learning 10-01/02)'),
  ('household_events', 'iot', NULL, '2026-10-02 11:45:00', '2026-10-02 11:48:00', 'test burst: 4 device events in one minute (todo_transition_learning 10-01/02)');

-- Seed: the ESPHome climate node (athom-tem-hum-sensor-4a4734) power-cycled 2026-09-27 02:40 UTC
-- and returned as ids 37893-37897 instead of 37885-37889. The old ids are in no snapshot. The
-- mapping below is INFERRED, not observed: same relative order, the same +8 offset, and matching
-- row counts (temperature/humidity ~144k each, the two wifi sensors identical, uptime rarely
-- changes). Verify against the node's real entity list if it ever matters.
INSERT IGNORE INTO `sa_sensor_aliases` (`smarthome_device_id`, `sensor_key`, `evidence`) VALUES
  (37885, 'athom-tem-hum-sensor-4a4734.local:Temperature', 'inferred: id order +8 and row counts vs 37893 (power-cycle 2026-09-27)'),
  (37886, 'athom-tem-hum-sensor-4a4734.local:Uptime Sensor', 'inferred: id order +8 and row counts vs 37894 (power-cycle 2026-09-27)'),
  (37887, 'athom-tem-hum-sensor-4a4734.local:WiFi Signal dB', 'inferred: id order +8 and row counts vs 37895 (power-cycle 2026-09-27)'),
  (37888, 'athom-tem-hum-sensor-4a4734.local:WiFi Signal Percent', 'inferred: id order +8 and row counts vs 37896 (power-cycle 2026-09-27)'),
  (37889, 'athom-tem-hum-sensor-4a4734.local:Humidity', 'inferred: id order +8 and row counts vs 37897 (power-cycle 2026-09-27)');
