-- Migration 007: Device Types Expansion
-- Add HA/ST device domains to device_types table for proper categorization

INSERT IGNORE INTO device_types (type) VALUES ('fan');
INSERT IGNORE INTO device_types (type) VALUES ('climate');
INSERT IGNORE INTO device_types (type) VALUES ('cover');
INSERT IGNORE INTO device_types (type) VALUES ('lock');
INSERT IGNORE INTO device_types (type) VALUES ('media_player');
INSERT IGNORE INTO device_types (type) VALUES ('sensor');
INSERT IGNORE INTO device_types (type) VALUES ('binary_sensor');
INSERT IGNORE INTO device_types (type) VALUES ('camera');
