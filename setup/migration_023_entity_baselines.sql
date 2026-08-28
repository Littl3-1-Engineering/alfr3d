-- Migration 023: Rhythm-break anomaly cards -- entity_baselines table
--
-- Per-entity rolling stats (median on-time, typical active hour, typical daily range) computed
-- from existing device_history/device_command_history by alfr3ddaemon.compute_entity_baselines()
-- every 6 hours. check_rhythm_break_anomaly() compares current state against these to fire a
-- card only on genuine deviation. See todo/todo_rhythm_break_anomaly.md.

CREATE TABLE `entity_baselines` (
  `id` INTEGER UNIQUE AUTO_INCREMENT,
  `entity_type` ENUM('device','smarthome_device') NOT NULL,
  `entity_id` INTEGER NOT NULL,
  `median_on_minutes` FLOAT NULL DEFAULT NULL,
  `typical_active_hour` TINYINT NULL DEFAULT NULL,
  `typical_daily_min` FLOAT NULL DEFAULT NULL,
  `typical_daily_max` FLOAT NULL DEFAULT NULL,
  `sample_count` INTEGER NOT NULL DEFAULT 0,
  `computed_at` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_entity` (`entity_type`, `entity_id`)
);
