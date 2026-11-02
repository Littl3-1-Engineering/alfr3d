-- Migration 053: add 'switch' to device_types
-- HA/Tuya smart plugs and relays sync into smarthome_devices as device_type 'switch'
-- (see common/ha_utils.py), but the LAN-device registry's device_types table never had
-- a matching row, so a plug could not be given an accurate type there (it had to be
-- mislabelled 'light').
-- device_types.type has no UNIQUE key, so INSERT IGNORE would NOT dedupe (it inserted a second
-- 'switch' row on a DB where the type had already been added by hand); guard with NOT EXISTS.
INSERT INTO device_types (type)
SELECT 'switch' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM device_types WHERE type = 'switch');
