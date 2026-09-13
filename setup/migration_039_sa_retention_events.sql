-- Migration 039 (2026-09-13): move SA event-log retention + storage-metrics recording
-- from Python `schedule` jobs to DB-native scheduled EVENTs.
--
-- household_events/attention_telemetry_history/card_interactions retention, and the daily
-- sa_storage_metrics snapshot, were all Python functions in alfr3ddaemon.py registered on the
-- daemon's own `schedule` loop. That means every one of them stopped running the moment
-- service-daemon was down, redeploying, or crash-looping -- retention and growth-tracking both
-- silently paused for as long as one particular container happened to be unhealthy, with
-- nothing else in the stack aware that had happened.
--
-- device_location_history's own retention (migration 036/038) was never like this -- it has
-- always been a scheduled EVENT living inside MySQL itself, enforced by the database engine
-- regardless of which application containers are up. This migration brings the other three
-- retention rules, and the storage-metrics snapshot, in line with that same pattern: what the
-- database can enforce natively, the database enforces -- not a long-running service process.
--
-- Retention windows (730 days each) are now literals in these EVENT bodies, the same way
-- device_location_history's already were -- there is no Python env-var override for any of
-- these four any more. Changing a window is a migration, same as it already was for
-- device_location_history. That is the real, accepted tradeoff of pushing this to the DB layer:
-- less runtime-configurable, but correct and running independent of application uptime.

DROP EVENT IF EXISTS `cleanup_household_events_event`;
CREATE EVENT `cleanup_household_events_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM household_events WHERE occurred_at < DATE_SUB(NOW(), INTERVAL 730 DAY);

DROP EVENT IF EXISTS `cleanup_attention_telemetry_history_event`;
CREATE EVENT `cleanup_attention_telemetry_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM attention_telemetry_history WHERE reported_at < DATE_SUB(NOW(), INTERVAL 730 DAY);

DROP EVENT IF EXISTS `cleanup_card_interactions_event`;
CREATE EVENT `cleanup_card_interactions_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM card_interactions WHERE occurred_at < DATE_SUB(NOW(), INTERVAL 730 DAY);

-- record_sa_storage_metrics_proc() replaces the Python function of the same purpose. Loops over
-- a fixed table-name list via a derived-table cursor (MySQL has no array literal) -- the same
-- cursor-over-a-small-set shape maintain_device_history_partitions() already uses for its own
-- partition list (migration 025). information_schema.TABLES' ROW_COUNT/DATA_LENGTH/INDEX_LENGTH
-- are InnoDB estimates, not exact counts -- fine for a growth trend, as documented on
-- sa_storage_metrics itself (migration 037).
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

DROP EVENT IF EXISTS `record_sa_storage_metrics_event`;
CREATE EVENT `record_sa_storage_metrics_event`
ON SCHEDULE EVERY 1 DAY
DO
   CALL record_sa_storage_metrics_proc();
