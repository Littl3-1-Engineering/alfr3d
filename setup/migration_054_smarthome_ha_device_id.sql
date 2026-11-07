-- Migration 054: smarthome_devices.ha_device_id
-- Home Assistant entity_ids change when an entity is renamed, but the HA *device* id (and the MAC
-- in its connections) does not. sync_ha_devices() keys rows by entity_id, so a rename used to
-- leave the old row behind as an immortal "online" ghost (frozen state, commands that silently
-- hit nothing) next to a fresh row for the new entity_id -- and any Quick Control pinned on the
-- old row pointed at the ghost. ha_device_id lets the sync recognise a rename and re-point the
-- existing row (keeping its favorites) instead of orphaning it.
ALTER TABLE `smarthome_devices`
  ADD COLUMN `ha_device_id` VARCHAR(64) NULL,
  ADD INDEX `idx_smarthome_ha_device_id` (`ha_device_id`);
