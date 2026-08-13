-- Migration 017: Deduplicate smarthome_devices and restore the unique key
--
-- Problem: sync_ha_devices()/sync_st_devices() rely on
-- INSERT ... ON DUPLICATE KEY UPDATE. That only dedupes when the
-- unique_source_device unique key (source, COALESCE(ha_entity_id, st_device_id))
-- exists on smarthome_devices. That key is missing on some live databases, so
-- every 15-minute sync inserted fresh copies of every HA entity -- flooding the
-- Domain DEVICES page with tens of thousands of rows (hundreds of copies per
-- entity) and making the frontend unresponsive ("Page unresponsive").
--
-- This migration:
--   1. Repoints device_command_history rows to the surviving (lowest-id) row
--   2. Deletes duplicate smarthome_devices rows, keeping the lowest id
--   3. Recreates unique_source_device so future syncs upsert in place

-- 1. Repoint command history to the surviving (lowest-id) row per entity
UPDATE device_command_history h
JOIN smarthome_devices s ON h.smarthome_device_id = s.id
JOIN (
    SELECT source, COALESCE(ha_entity_id, st_device_id) AS entity, MIN(id) AS keep_id
    FROM smarthome_devices
    WHERE COALESCE(ha_entity_id, st_device_id) IS NOT NULL
    GROUP BY source, COALESCE(ha_entity_id, st_device_id)
) k ON k.source = s.source AND k.entity = COALESCE(s.ha_entity_id, s.st_device_id)
SET h.smarthome_device_id = k.keep_id
WHERE h.smarthome_device_id <> k.keep_id;

-- 2. Delete duplicate rows, keeping the lowest id per source/entity.
--    Uses a single-pass GROUP BY (no self-join) so it stays fast without an
--    index on ha_entity_id.
DELETE FROM smarthome_devices
WHERE id NOT IN (
    SELECT keep_id
    FROM (
        SELECT MIN(id) AS keep_id
        FROM smarthome_devices
        WHERE COALESCE(ha_entity_id, st_device_id) IS NOT NULL
        GROUP BY source, COALESCE(ha_entity_id, st_device_id)
    ) keep
);

-- 3. Restore the unique key so future syncs upsert in place
ALTER TABLE `smarthome_devices`
    ADD UNIQUE KEY `unique_source_device` (`source`, (COALESCE(`ha_entity_id`, `st_device_id`)));
