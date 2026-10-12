-- Migration 048 (2026-10-12): keep the shadow comparison as history.
--
-- SA learners run beside the legacy rules and log `SHADOW <rule> AGREE|DIFFER`, but those lines
-- lived only in the container log and vanished on every restart, so the week of evidence the rule
-- cutover review needs could not be counted (todo/sa/todo_lf4b_baseline_ports.md). This table
-- appends one row each time a rule's (legacy, learner) pair CHANGES, the same moment the log line
-- is written, so it stays small: a held state is one row, not one per minute.
--
--   * verdict is 'AGREE' or 'DIFFER';
--   * legacy / learner are the same descriptions the log carries ('quiet' when nothing fired);
--   * learner_count is how many findings the learner had.
--
-- Written best-effort by sa-awareness, so it can never fail a cycle. observed_at is UTC.
-- 730-day retention like the other SA tables.

CREATE TABLE IF NOT EXISTS `sa_shadow_comparison` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `rule_id` VARCHAR(64) NOT NULL,
  `observed_at` DATETIME NOT NULL,
  `verdict` VARCHAR(8) NOT NULL,
  `legacy` TEXT NOT NULL,
  `learner` TEXT NOT NULL,
  `learner_count` INT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_sa_shadow_comparison_rule_observed` (`rule_id`, `observed_at`),
  KEY `idx_sa_shadow_comparison_observed_at` (`observed_at`)
);

DROP EVENT IF EXISTS `cleanup_sa_shadow_comparison_event`;
CREATE EVENT `cleanup_sa_shadow_comparison_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM sa_shadow_comparison WHERE observed_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 730 DAY);
