-- Migration 050: entity_baselines.active_hours_mask -- the hours a device is usually online
--
-- typical_active_hour is the modal session *start* hour, a single point. The rhythm-break
-- "unusual hour" check treated it as the centre of the device's active window and flagged any
-- device still on more than 4 hours later -- i.e. a work machine that starts at 8:45 raised
-- "on at an unusual hour" every afternoon. active_hours_mask is a 24-bit mask (bit h = UTC hour
-- h) of the hours the device was actually online on a meaningful share of days, so the check can
-- ask "is this an hour the device is ever on?". NULL until compute_entity_baselines() next runs;
-- the unusual-hour check stays silent for NULL.
ALTER TABLE `entity_baselines`
  ADD COLUMN `active_hours_mask` INT UNSIGNED NULL DEFAULT NULL AFTER `typical_last_activity_hour`;
