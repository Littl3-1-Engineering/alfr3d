-- Migration 040 (SA-9 Phase 2): smarthome_sensor_history table
--
-- Durable numeric-reading history for smarthome/ESPHome sensor entities. Nothing kept one
-- before this -- both the ESPHome poll sync and Phase 5 push only ever overwrote
-- `smarthome_devices.last_state` in place, so there was never anything to compute a "typical for
-- this time of day" baseline from. Source-agnostic name/shape (keyed to `smarthome_devices.id`,
-- which already carries `source`) even though only the ESPHome write path populates it today --
-- see services/common/esphome_utils.py's _upsert_node_entities()/_handle_state_push().
CREATE TABLE `smarthome_sensor_history` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `smarthome_device_id` INT NOT NULL,
  `value` FLOAT NOT NULL,
  `recorded_at` DATETIME NOT NULL,
  INDEX `idx_smarthome_sensor_history_device_recorded` (`smarthome_device_id`, `recorded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Retention: 730 days, matching the household's other SA event-log tables (household_events/
-- attention_telemetry_history/card_interactions/device_location_history -- see migration 039's
-- own comment for why this lives as a DB-native EVENT, not a Python schedule job.
DROP EVENT IF EXISTS `cleanup_smarthome_sensor_history_event`;
DELIMITER ;;
CREATE EVENT `cleanup_smarthome_sensor_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM smarthome_sensor_history WHERE recorded_at < DATE_SUB(NOW(), INTERVAL 730 DAY);
DELIMITER ;

-- Bring this table into the existing storage-growth tracking (migration 039) from day one,
-- rather than a separate follow-up migration purely to add one more UNION ALL branch.
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
