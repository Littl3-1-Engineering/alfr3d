-- Migration 037 (2026-09-13): sa_storage_metrics table
--
-- Daily snapshot of row count and on-disk size for the tables
-- alfr3ddaemon.SA_STORAGE_METRICS_TRACKED_TABLES names, written by
-- record_sa_storage_metrics(). Turns todo/todo_sa_data_retention_3yr.md's ~2-week production
-- estimate into a real, growing time series that can be checked against reality directly:
--
--   SELECT table_name, recorded_at, row_count,
--          ROUND((data_bytes+index_bytes)/1024/1024, 2) AS size_mb
--   FROM sa_storage_metrics ORDER BY table_name, recorded_at;
--
-- No retention on this table itself, deliberately: one row per tracked table per day means
-- six tables x 365 days x 3 years is ~6,570 rows total -- the metrics log costs less disk than
-- any single table it's measuring.

CREATE TABLE IF NOT EXISTS `sa_storage_metrics` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `table_name` VARCHAR(64) NOT NULL,
    `row_count` BIGINT UNSIGNED NOT NULL,
    `data_bytes` BIGINT UNSIGNED NOT NULL,
    `index_bytes` BIGINT UNSIGNED NOT NULL,
    `recorded_at` DATETIME NOT NULL,
    INDEX `idx_sa_storage_metrics_table_recorded` (`table_name`, `recorded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
