-- Migration 019: ESPHome integration
--
-- Adds a per-entity ID column to smarthome_devices (mirrors ha_entity_id/st_device_id -- one row
-- per exposed entity, not per physical node) and a new esphome_nodes table that tracks discovered
-- and accepted ESPHome nodes (hostname/IP/port/PSK), separate from smarthome_devices since a node
-- has one connection but many entities. See todo/todo_esphome.md for full design.
--
-- esp_entity_id is formatted "<node_hostname>:<entity_key>" (ESPHome's native API keys entities
-- by an internal int, not a string like HA's entity_id).

ALTER TABLE `smarthome_devices` ADD COLUMN `esp_entity_id` VARCHAR(160) NULL;

-- Extend the unique key to include the new ID column (drop/recreate, per
-- migration_017_iot_dedupe.sql's pattern for the same key).
ALTER TABLE `smarthome_devices` DROP INDEX `unique_source_device`;
ALTER TABLE `smarthome_devices`
    ADD UNIQUE KEY `unique_source_device`
        (`source`, (COALESCE(`ha_entity_id`, `st_device_id`, `esp_entity_id`)));

-- ESPHome nodes: rows with accepted=FALSE are mDNS-discovered candidates not yet linked;
-- accepted=TRUE rows are connectable (PSK, if the node uses one, stored here -- plaintext for v1,
-- see todo/todo_encrypt_secrets_at_rest.md). Discovery scans upsert rows here but never flip
-- accepted to TRUE themselves -- that requires the explicit
-- POST /api/iot/esphome/discovered/{hostname}/accept action (mDNS discovery isn't account-scoped
-- like HA/ST, so nodes must not auto-link; see todo/todo_esphome.md Design section 1).
CREATE TABLE IF NOT EXISTS `esphome_nodes` (
  `id` INTEGER UNIQUE AUTO_INCREMENT,
  `hostname` VARCHAR(255) NOT NULL,
  `ip_address` VARCHAR(45) NULL,
  `port` INTEGER NOT NULL DEFAULT 6053,
  `name` VARCHAR(128) NULL,
  `psk` VARCHAR(255) NULL,
  `accepted` BOOLEAN NOT NULL DEFAULT FALSE,
  `last_seen` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `accepted_at` TIMESTAMP NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_hostname` (`hostname`)
);

-- ESPHome is an always-on parallel provider, not folded into the single-select `iot_provider`
-- config value used to pick between HA/SmartThings (see todo/todo_esphome.md Design section 5's
-- fix to /api/iot/devices, which stops treating that value as an exclusive filter).
INSERT IGNORE INTO config (name, value) VALUES ('esphome_enabled', 'true');
