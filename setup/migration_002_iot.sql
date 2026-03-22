-- Migration 002: IoT Integration (Home Assistant + SmartThings)
-- Creates smarthome_devices table for HA/ST support and device command history

-- Create smarthome_devices table
CREATE TABLE IF NOT EXISTS `smarthome_devices` (
  `id` INTEGER UNIQUE AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `source` VARCHAR(32) DEFAULT 'homeassistant',
  `mac_address` VARCHAR(17) NULL,
  `ha_entity_id` VARCHAR(128) NULL,
  `st_device_id` VARCHAR(128) NULL,
  `st_location_id` VARCHAR(128) NULL,
  `device_type` VARCHAR(64) NOT NULL,
  `room` VARCHAR(128) NULL,
  `capabilities` JSON NULL,
  `online` BOOLEAN DEFAULT TRUE,
  `last_state` JSON NULL,
  `environment_id` INTEGER NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_source_device` (`source`, COALESCE(ha_entity_id, st_device_id))
);

-- Create device_command_history table
CREATE TABLE IF NOT EXISTS `device_command_history` (
  `id` INTEGER UNIQUE AUTO_INCREMENT,
  `smarthome_device_id` INTEGER NOT NULL,
  `command` VARCHAR(64) NOT NULL,
  `params` JSON NULL,
  `result` VARCHAR(64) NULL,
  `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
);

-- Add foreign keys
ALTER TABLE `smarthome_devices` ADD FOREIGN KEY (`environment_id`) REFERENCES `environment` (`id`);
ALTER TABLE `device_command_history` ADD FOREIGN KEY (`smarthome_device_id`) REFERENCES `smarthome_devices` (`id`);

-- Create scheduled event for cleanup
DROP EVENT IF EXISTS `cleanup_device_command_history_event`;
DELIMITER ;;
CREATE EVENT `cleanup_device_command_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM device_command_history WHERE timestamp < DATE_SUB(NOW(), INTERVAL 180 DAY);
DELIMITER ;

-- Add IoT config entries
INSERT IGNORE INTO config (name, value) VALUES ('iot_provider', 'homeassistant');
INSERT IGNORE INTO config (name, value) VALUES ('ha_url', '');
INSERT IGNORE INTO config (name, value) VALUES ('ha_token', '');
INSERT IGNORE INTO config (name, value) VALUES ('st_pat', '');
