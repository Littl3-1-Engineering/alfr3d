-- Migration 026: durable household event log
--
-- Every event-stream message currently lands only in service_api's in-memory
-- recent_events buffer (last 20, RAM-only, gone on restart). household_events
-- is a second, durable destination for the same messages -- SA-3/SA-10/SA-12
-- and future "what usually happens next" reasoning need real accumulated
-- history to query. See todo/todo_household_event_log.md.

CREATE TABLE `household_events` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `event_type` VARCHAR(32) NOT NULL COMMENT 'mirrors the event-stream message''s loose type string',
  `message` TEXT NULL DEFAULT NULL COMMENT 'prose; some producers (personality_state) have none',
  `occurred_at` DATETIME NOT NULL,
  `source_service` VARCHAR(32) NOT NULL,
  INDEX `idx_household_events_type_occurred` (`event_type`, `occurred_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
