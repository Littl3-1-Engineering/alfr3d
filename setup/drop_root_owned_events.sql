-- One-time fix for installs whose legacy retention events were created by root
-- (createTables.sql loaded as root): cleanup_device_history_event,
-- cleanup_calendar_events_event, cleanup_device_command_history_event.
--
-- MySQL 8 requires SYSTEM_USER to drop an event whose DEFINER holds it, and the app's
-- migration account doesn't have it. Migration 0048 needs these gone (they would keep
-- deleting device_history and calendar rows older than 180 days / 24 hours, defeating the
-- 730-day retention), so it stops with instructions if it can't drop them itself.
--
-- Run as root against the app database, then re-run the migration:
--   docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
--     < setup/drop_root_owned_events.sql
--
-- Safe to run more than once. Take a mysqldump backup first, as before any migration.

DROP EVENT IF EXISTS `cleanup_device_history_event`;
DROP EVENT IF EXISTS `cleanup_calendar_events_event`;
DROP EVENT IF EXISTS `cleanup_device_command_history_event`;
