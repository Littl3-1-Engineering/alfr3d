-- Migration 020: Camera stream URL on device
--
-- Adds a per-device RTSP stream URL so camera devices (device_type = 'camera') can be
-- streamed via the Nexus camera panel without a global STREAM_CAMERA_URL env var. Nullable --
-- most devices aren't cameras and never set it. See todo/todo_camera_streaming.md.

ALTER TABLE `device` ADD COLUMN `stream_url` VARCHAR(512) NULL DEFAULT NULL;
