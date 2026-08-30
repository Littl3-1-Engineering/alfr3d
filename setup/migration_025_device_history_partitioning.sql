-- Migration 025: partition device_history by month for cheap retention.
--
-- device_history has no cleanup mechanism beyond a daily row-by-row DELETE
-- (cleanup_device_history_event, from createTables.sql). That EVENT never
-- shrinks the InnoDB tablespace and gets more expensive as the table grows.
-- RANGE partitioning by month lets retention become DROP PARTITION, which is
-- near-instant and actually frees disk.
--
-- InnoDB does not support foreign keys on partitioned tables, so the three
-- FKs on device_history (device_id, environment_id, user_id) are dropped as
-- part of this change -- by the calling migration, via drop_foreign_keys_for_column,
-- before this file runs. The app never relied on cascade behavior here (none
-- of the three were declared ON DELETE CASCADE/SET NULL), so this trades
-- DB-enforced referential integrity on a pure audit-log table for the
-- ability to partition it -- app-level FK checks, if any are needed, stay
-- the app's responsibility going forward.
--
-- cleanup_device_history_event is dropped by the calling migration too, not
-- here: it was DEFINER=root (createTables.sql runs as root), and dropping a
-- SYSTEM_USER-owned event needs SYSTEM_USER, which the app's migration
-- account doesn't have. See run_sql.py's event_exists() docstring.

-- Partition on the day of `timestamp`. One partition per calendar month,
-- pre-created a few months ahead; `p_future` catches anything beyond that
-- until the maintenance procedure below extends the horizon.
ALTER TABLE `device_history`
  PARTITION BY RANGE (TO_DAYS(`timestamp`)) (
    PARTITION p_2026_06 VALUES LESS THAN (TO_DAYS('2026-07-01')),
    PARTITION p_2026_07 VALUES LESS THAN (TO_DAYS('2026-08-01')),
    PARTITION p_2026_08 VALUES LESS THAN (TO_DAYS('2026-09-01')),
    PARTITION p_2026_09 VALUES LESS THAN (TO_DAYS('2026-10-01')),
    PARTITION p_2026_10 VALUES LESS THAN (TO_DAYS('2026-11-01')),
    PARTITION p_2026_11 VALUES LESS THAN (TO_DAYS('2026-12-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
  );

DROP PROCEDURE IF EXISTS `maintain_device_history_partitions`;

DELIMITER ;;
CREATE PROCEDURE `maintain_device_history_partitions`(IN retention_days INT, IN horizon_months INT)
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE part_name VARCHAR(64);
  DECLARE part_desc VARCHAR(64);
  DECLARE cutoff_days INT;
  DECLARE i INT DEFAULT 1;
  DECLARE next_boundary_days INT;
  DECLARE next_part_name VARCHAR(64);
  DECLARE cur CURSOR FOR
    SELECT PARTITION_NAME, PARTITION_DESCRIPTION
    FROM information_schema.PARTITIONS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'device_history'
      AND PARTITION_NAME IS NOT NULL
      AND PARTITION_DESCRIPTION <> 'MAXVALUE';
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  SET cutoff_days = TO_DAYS(DATE_SUB(CURDATE(), INTERVAL retention_days DAY));

  -- Drop whole partitions that are entirely older than the retention cutoff.
  OPEN cur;
  drop_loop: LOOP
    FETCH cur INTO part_name, part_desc;
    IF done THEN
      LEAVE drop_loop;
    END IF;
    IF CAST(part_desc AS UNSIGNED) <= cutoff_days THEN
      SET @sql = CONCAT('ALTER TABLE `device_history` DROP PARTITION `', part_name, '`');
      PREPARE stmt FROM @sql;
      EXECUTE stmt;
      DEALLOCATE PREPARE stmt;
    END IF;
  END LOOP;
  CLOSE cur;

  -- Ensure partitions exist out to horizon_months from the current month,
  -- splitting the trailing p_future partition one month at a time.
  SET i = 1;
  extend_loop: WHILE i <= horizon_months DO
    SET next_boundary_days = TO_DAYS(DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL i MONTH));
    SET next_part_name = CONCAT('p_', DATE_FORMAT(DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL (i - 1) MONTH), '%Y_%m'));
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.PARTITIONS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'device_history'
        AND PARTITION_DESCRIPTION = CAST(next_boundary_days AS CHAR)
    ) THEN
      SET @sql = CONCAT(
        'ALTER TABLE `device_history` REORGANIZE PARTITION `p_future` INTO (',
        'PARTITION `', next_part_name, '` VALUES LESS THAN (', next_boundary_days, '), ',
        'PARTITION `p_future` VALUES LESS THAN MAXVALUE)'
      );
      PREPARE stmt FROM @sql;
      EXECUTE stmt;
      DEALLOCATE PREPARE stmt;
    END IF;
    SET i = i + 1;
  END WHILE;
END;;
DELIMITER ;

DROP EVENT IF EXISTS `maintain_device_history_partitions_event`;
CREATE EVENT `maintain_device_history_partitions_event`
ON SCHEDULE EVERY 1 DAY
DO
  CALL maintain_device_history_partitions(180, 3);
