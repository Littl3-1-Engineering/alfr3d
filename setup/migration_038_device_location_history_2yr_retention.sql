-- Migration 038 (2026-09-13): device_location_history retention 180 days -> 730 days (2 years)
--
-- Raises this table's retention to match the other SA event-log tables
-- (household_events/attention_telemetry_history/card_interactions -- see
-- alfr3ddaemon.SA_EVENT_LOG_RETENTION_DAYS_DEFAULT), so multi-season location baselines are
-- possible for the same reason the others were raised: a rolling 180-day window can never
-- contain both winter and summer.
--
-- This table's retention lives in a MySQL-native scheduled EVENT (migration 036), not a
-- Python-side env-configurable constant like its three siblings -- that asymmetry is real and
-- not fixed here; recreating the event is the correct, minimal fix for the number itself.
-- cleanup_device_location_history_event is owned by this deployment's own migration user (not
-- root/SYSTEM_USER, unlike device_history's original event), so DROP+CREATE from a normal
-- migration is safe -- see run_sql.py's event_exists() docstring for why that distinction
-- matters here.

DROP EVENT IF EXISTS `cleanup_device_location_history_event`;
DELIMITER ;;
CREATE EVENT `cleanup_device_location_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM device_location_history WHERE captured_at < DATE_SUB(NOW(), INTERVAL 730 DAY);
DELIMITER ;
