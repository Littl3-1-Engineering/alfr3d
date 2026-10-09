-- Migration 043 (2026-10-09): close the SA retention gaps left by migration 039.
--
-- Migration 039 moved four event-log tables to 730 days. Every other variable the SA learning
-- foundation needs was still short-lived or not kept at all -- see
-- todo/sa/todo_lf0_retention_gaps.md:
--   - device_history: 180 days (partition drop, migration 025)
--   - weather: no history at all, the environment row is overwritten every 1-4 h
--   - calendar_events: deleted 24 h after each event ends
--   - listening_history: unbounded
--   - device_command_history: no writer ever existed (IoT commands go to household_events)
--
-- The three legacy root-owned events (cleanup_device_history_event,
-- cleanup_calendar_events_event, cleanup_device_command_history_event) are dropped by the
-- calling migration (0048) before this file runs, or by setup/drop_root_owned_events.sql as
-- root when the migration account lacks SYSTEM_USER. They are not dropped here.

-- device_history: keep 730 days of monthly partitions (was 180).
DROP EVENT IF EXISTS `maintain_device_history_partitions_event`;
CREATE EVENT `maintain_device_history_partitions_event`
ON SCHEDULE EVERY 1 DAY
DO
  CALL maintain_device_history_partitions(730, 3);

-- calendar_events: keep past events for 730 days (was 24 h). sync_calendar() only deletes
-- rows inside its forward window (end_time >= now), so past events survive every sync.
DROP EVENT IF EXISTS `cleanup_calendar_events_event`;
CREATE EVENT `cleanup_calendar_events_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM calendar_events WHERE end_time < DATE_SUB(NOW(), INTERVAL 730 DAY);

-- listening_history: was unbounded.
DROP EVENT IF EXISTS `cleanup_listening_history_event`;
CREATE EVENT `cleanup_listening_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM listening_history WHERE played_at < DATE_SUB(NOW(), INTERVAL 730 DAY);

-- environment_history: one snapshot of the environment row per weather/forecast update,
-- written by service_environment/weather_util.py right after each UPDATE commits. Python,
-- not a trigger: with binary logging on and log_bin_trust_function_creators=0, the app's
-- migration account can't create triggers. recorded_at is UTC (UTC_TIMESTAMP()).
CREATE TABLE IF NOT EXISTS `environment_history` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `environment_id` INT NOT NULL,
  `kind` ENUM('weather', 'forecast') NOT NULL,
  `recorded_at` DATETIME NOT NULL,
  `latitude` DECIMAL(20,10) NULL,
  `longitude` DECIMAL(20,10) NULL,
  `city` VARCHAR(64) NULL,
  `description` VARCHAR(64) NULL,
  `low` INT NULL,
  `high` INT NULL,
  `temperature` FLOAT NULL,
  `wind` FLOAT NULL,
  `wind_dir` VARCHAR(16) NULL,
  `sunrise` DATETIME NULL,
  `sunset` DATETIME NULL,
  `pressure` INT NULL,
  `pressure_trend` VARCHAR(8) NULL,
  `humidity` INT NULL,
  `subjective_feel` VARCHAR(64) NULL,
  `forecast_rain_probability` FLOAT NULL,
  `forecast_temp` FLOAT NULL,
  `forecast_conditions` VARCHAR(64) NULL,
  `forecast_updated_at` DATETIME NULL,
  `timezone` INT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_environment_history_recorded_at` (`recorded_at`),
  KEY `idx_environment_history_env_recorded_at` (`environment_id`, `recorded_at`)
);

DROP EVENT IF EXISTS `cleanup_environment_history_event`;
CREATE EVENT `cleanup_environment_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM environment_history WHERE recorded_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 730 DAY);

-- device_command_history: dead table, never written. Its FK to smarthome_devices only made
-- DELETE /api/iot/devices/{id} clear it first.
DROP TABLE IF EXISTS `device_command_history`;

-- Track the newly retained tables' growth too.
DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;

DELIMITER ;;
CREATE PROCEDURE `record_sa_storage_metrics_proc`()
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE tbl VARCHAR(64);
  DECLARE cur CURSOR FOR
    SELECT name FROM (
      SELECT 'household_events' AS name
      UNION ALL SELECT 'card_interactions'
      UNION ALL SELECT 'attention_telemetry_history'
      UNION ALL SELECT 'device_location_history'
      UNION ALL SELECT 'entity_baselines'
      UNION ALL SELECT 'device_history'
      UNION ALL SELECT 'smarthome_sensor_history'
      UNION ALL SELECT 'environment_history'
      UNION ALL SELECT 'calendar_events'
      UNION ALL SELECT 'listening_history'
    ) AS tracked_tables;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO tbl;
    IF done THEN
      LEAVE read_loop;
    END IF;
    INSERT INTO sa_storage_metrics (table_name, row_count, data_bytes, index_bytes, recorded_at)
    SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, NOW()
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl;
  END LOOP;
  CLOSE cur;
END;;
DELIMITER ;
