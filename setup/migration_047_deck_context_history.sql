-- Migration 047 (2026-10-10): keep the Deck's device context and surface state as history.
--
-- POST /api/context/device-snapshot and /context/surface-state used to overwrite one `config`
-- JSON value per Deck, so battery / charging / DND / headset / network / orientation / active
-- surface / top app / terminal session / speech relay were current-value-only and everything
-- before the last report was lost (todo/sa/todo_deck_learning_stream.md). This table appends a
-- row when a Deck's reported state CHANGES, plus a heartbeat row (is_heartbeat = 1) when nothing
-- has changed for 30 minutes, so a held state and a silent Deck can be told apart:
--
--   * change-only writes: battery is bucketed to 5 % (a slow drain is not a row a minute);
--   * the tri-state survives: a column is NULL when the report did not carry that facet
--     (unknown), never 0 or false;
--   * `source` is 'device_snapshot' (per Deck, device_install_id set) or 'surface_state' (the
--     older single-launcher report, device_install_id NULL).
--
-- Written best-effort from the two API routes after the existing config upsert, so it can never
-- fail a report. observed_at is UTC. 730-day retention like the other SA tables.

CREATE TABLE IF NOT EXISTS `deck_context_history` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `source` VARCHAR(16) NOT NULL,
  `device_install_id` CHAR(36) NULL,
  `observed_at` DATETIME(3) NOT NULL,
  `battery_bucket` TINYINT UNSIGNED NULL,
  `is_charging` TINYINT(1) NULL,
  `dnd_active` TINYINT(1) NULL,
  `headset_connected` TINYINT(1) NULL,
  `network_type` VARCHAR(16) NULL,
  `network_quality` VARCHAR(32) NULL,
  `orientation` VARCHAR(16) NULL,
  `active_surface` VARCHAR(64) NULL,
  `top_app` VARCHAR(128) NULL,
  `terminal_session_active` TINYINT(1) NULL,
  `relay_enabled` TINYINT(1) NULL,
  `is_heartbeat` TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_deck_context_history_observed_at` (`observed_at`),
  KEY `idx_deck_context_history_device_observed_at` (`device_install_id`, `source`, `observed_at`)
);

DROP EVENT IF EXISTS `cleanup_deck_context_history_event`;
CREATE EVENT `cleanup_deck_context_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM deck_context_history WHERE observed_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 730 DAY);

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
      UNION ALL SELECT 'sa_inferences'
      UNION ALL SELECT 'deck_context_history'
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
