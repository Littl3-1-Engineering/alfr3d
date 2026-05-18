-- Migration 001: Replace calendar cleanup trigger with scheduled event
-- This migration removes the AFTER INSERT trigger on calendar_events and adds a daily scheduled event for cleanup

-- Drop the old trigger
DROP TRIGGER IF EXISTS `cleanup_old_calendar_events`;

-- Drop the event if it exists (in case of re-run)
DROP EVENT IF EXISTS `cleanup_calendar_events_event`;

-- Create the new scheduled event
DELIMITER ;;
CREATE EVENT `cleanup_calendar_events_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM calendar_events WHERE end_time < DATE_SUB(NOW(), INTERVAL 24 HOUR);
DELIMITER ;

-- Ensure event scheduler is enabled (run this separately if needed)
-- SET GLOBAL event_scheduler = ON;
