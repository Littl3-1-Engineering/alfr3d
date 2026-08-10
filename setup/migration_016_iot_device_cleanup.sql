-- Migration 016: Clean up auto-created device rows from HA/ST sync
--
-- Past sync_ha_devices()/sync_st_devices() runs auto-created a `device` row
-- (IP = '0.0.0.0', guest type) for every smarthome device that had no MAC
-- match in the device table. This flooded the Domain page with junk devices.
-- Phase 16 removes the auto-create behavior going forward; this migration
-- removes the rows that were already created.
--
-- Order matters because of FK constraints:
--   1. device_history.device_id  -> device.id
--   2. smarthome_devices.device_id -> device.id
--   3. device_history.device_id  -> device.id

-- 1. Remove history entries for auto-created devices
DELETE FROM device_history
WHERE device_id IN (SELECT id FROM device WHERE IP = '0.0.0.0');

-- 2. Unlink smarthome devices that point at auto-created device rows
UPDATE smarthome_devices
SET device_id = NULL
WHERE device_id IN (SELECT id FROM device WHERE IP = '0.0.0.0');

-- 3. Delete the auto-created device rows
DELETE FROM device WHERE IP = '0.0.0.0';
