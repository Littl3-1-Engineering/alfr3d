-- Migration 028 (SA-2): attention_telemetry_history table
--
-- POST /api/context/attention-telemetry (routes/context.py) upserts the launcher's latest
-- rolling-window snapshot into `config` and nothing else -- "no history kept here" was the
-- explicit design until now. check_attention_focus()/check_wind_down_signal() could therefore
-- only ever compare the current snapshot to a fixed threshold, never to what's actually typical
-- for this household. This table is a second, additive destination for the same reports; the
-- `config` upsert is unchanged.
CREATE TABLE `attention_telemetry_history` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `unlock_count` INT NOT NULL,
    `switch_count` INT NOT NULL,
    `dwell_by_category_ms` JSON NOT NULL,
    `window_start_ms` BIGINT NOT NULL,
    `window_end_ms` BIGINT NOT NULL,
    `reported_at` DATETIME NOT NULL,
    INDEX `idx_attention_telemetry_history_reported_at` (`reported_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
