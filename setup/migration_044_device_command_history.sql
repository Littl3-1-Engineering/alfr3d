-- Migration 044 (2026-10-09): bring device_command_history back as a real command log.
--
-- Migration 043 dropped the original table because nothing had ever written to it. That was
-- the wrong call for SA learning: the household_events row the API emits per command keeps
-- only a collapsed verb (set_brightness/set_temperature/lock/volume_set all become "set"), has
-- no payload column, records successes only, and records nothing for the per-source control
-- endpoints. Command parameters are where preferences live (evening brightness, night setpoint,
-- usual volume), so they get their own table.
--
-- Written by common/device_commands.record_device_command(), called from the three low-level
-- senders (ha_control_device, st_control_device, control_esphome_device_async), so every
-- command is logged whatever issued it: API endpoints (origin 'user'), routines ('routine'),
-- audio casting and other internal callers ('system').
--
-- No foreign key to smarthome_devices: command history must outlive a removed device (same
-- reasoning as household_events' loose subject_id), and it no longer blocks
-- DELETE /api/iot/devices/{id}. smarthome_device_id is resolved at write time from the
-- source's own id (entity_ref) and is NULL when the device isn't known yet.
--
-- issued_at is UTC.

CREATE TABLE IF NOT EXISTS `device_command_history` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `smarthome_device_id` INT NULL,
  `source` VARCHAR(16) NOT NULL,
  `entity_ref` VARCHAR(128) NOT NULL,
  `command` VARCHAR(64) NOT NULL,
  `requested_command` VARCHAR(64) NULL,
  `params` JSON NULL,
  `success` TINYINT(1) NOT NULL,
  `message` VARCHAR(255) NULL,
  `origin` VARCHAR(16) NOT NULL,
  `user_id` INT NULL,
  `context` JSON NULL,
  `issued_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_device_command_history_issued_at` (`issued_at`),
  KEY `idx_device_command_history_device_issued_at` (`smarthome_device_id`, `issued_at`),
  KEY `idx_device_command_history_origin_issued_at` (`origin`, `issued_at`)
);

DROP EVENT IF EXISTS `cleanup_device_command_history_event`;
CREATE EVENT `cleanup_device_command_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM device_command_history WHERE issued_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 730 DAY);

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
      UNION ALL SELECT 'device_command_history'
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
