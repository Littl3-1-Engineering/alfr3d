-- Migration 053: add 'switch' to device_types
-- HA/Tuya smart plugs and relays sync into smarthome_devices as device_type 'switch'
-- (see common/ha_utils.py), but the LAN-device registry's device_types table never had
-- a matching row, so a plug could not be given an accurate type there (it had to be
-- mislabelled 'light'). INSERT IGNORE keeps this idempotent.
INSERT IGNORE INTO device_types (type) VALUES ('switch');
