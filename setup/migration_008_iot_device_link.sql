-- Migration 008: IoT Device FK Link
-- Adds device_id foreign key to link smarthome_devices to device table
-- Enables auto-linking during HA/ST sync

-- Add device_id column to smarthome_devices
ALTER TABLE smarthome_devices ADD COLUMN device_id INTEGER NULL;

-- Add foreign key constraint
ALTER TABLE smarthome_devices ADD FOREIGN KEY (device_id) REFERENCES device(id);

-- Add index for faster lookups
ALTER TABLE smarthome_devices ADD INDEX idx_device_id (device_id);
