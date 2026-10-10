-- Migration 046 (2026-10-10): the SA inference contract (LF-3, todo/sa/todo_lf3_presence_learner.md).
--
-- Two tables every learner and every rule shares, so a layer-2 inference can be built on a
-- layer-1 one without knowing which learner produced it (todo/sa/SA_ROADMAP.md).
--
--  sa_profiles    : what a learner has fitted -- one row per (learner, subject, signal), replaced
--                   on each fit. Written by sa-learner, read by sa-awareness. Replaces
--                   entity_baselines' per-type column reuse (retired in LF-4).
--  sa_inferences  : one scored statement about a subject over a window, with a probability and
--                   a confidence. A deviation ("away, but usually home") or a prediction
--                   ("P(home) over the next 24 h"). Layer 2 will write rows with layer = 2 whose
--                   `evidence` lists parent inference ids.
--
-- `probability` means: for a deviation, the probability the model gave the state that was
-- OBSERVED (small = surprising); for a prediction, the probability the signal is true at
-- window_start. `surprise` is -log2(probability), in bits. `confidence` is 0-1 and is defined once,
-- in sa/confidence.py: sufficiency x coverage x source_quality x stability.
--
-- `kind` is a VARCHAR, not an ENUM, so a new inference kind never needs a migration. All
-- timestamps are UTC. Retention is 730 days like every other SA table.

CREATE TABLE IF NOT EXISTS `sa_profiles` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `learner` VARCHAR(48) NOT NULL,
  `learner_version` VARCHAR(16) NOT NULL,
  `subject_type` VARCHAR(16) NOT NULL,
  `subject_id` VARCHAR(64) NOT NULL,
  `signal` VARCHAR(48) NOT NULL,
  `params` JSON NOT NULL,
  `n_eff` DOUBLE NULL,
  `coverage` DOUBLE NULL,
  `source_quality` DOUBLE NULL,
  `stability` DOUBLE NULL,
  `fitted_from` DATE NULL,
  `fitted_to` DATE NULL,
  `computed_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sa_profiles_key` (`learner`, `subject_type`, `subject_id`, `signal`),
  KEY `idx_sa_profiles_computed_at` (`computed_at`)
);

CREATE TABLE IF NOT EXISTS `sa_inferences` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `layer` TINYINT NOT NULL DEFAULT 1,
  `kind` VARCHAR(16) NOT NULL,
  `subject_type` VARCHAR(16) NOT NULL,
  `subject_id` VARCHAR(64) NOT NULL,
  `signal` VARCHAR(48) NOT NULL,
  `context` JSON NULL,
  `window_start` DATETIME NOT NULL,
  `window_end` DATETIME NULL,
  `observed` JSON NULL,
  `expected` JSON NULL,
  `probability` DOUBLE NULL,
  `surprise` DOUBLE NULL,
  `confidence` DOUBLE NULL,
  `n_eff` DOUBLE NULL,
  `evidence` JSON NULL,
  `learner` VARCHAR(48) NOT NULL,
  `learner_version` VARCHAR(16) NOT NULL,
  `computed_at` DATETIME NOT NULL,
  `expires_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sa_inferences_key` (`learner`, `kind`, `subject_type`, `subject_id`, `signal`, `window_start`),
  KEY `idx_sa_inferences_subject` (`subject_type`, `subject_id`, `signal`, `window_start`),
  KEY `idx_sa_inferences_computed_at` (`computed_at`)
);

DROP EVENT IF EXISTS `cleanup_sa_inferences_event`;
CREATE EVENT `cleanup_sa_inferences_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM sa_inferences WHERE computed_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 730 DAY);

-- Track sa_inferences' growth alongside the other SA tables.
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
