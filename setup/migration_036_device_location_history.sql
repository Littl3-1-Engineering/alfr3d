-- Migration 036: device_location_history table
--
-- Backs POST /api/context/device-location (routes/context.py): ALFR3D Deck reports its own
-- approximate geolocation once per background-sync window. Stored per *device* (keyed by the
-- Deck install's stable UUID `client_install_id`), not pre-aggregated to a user -- a
-- phone-in-pocket track and a tablet-left-at-home track are each individually accurate and
-- must not be merged (todo/todo_device_location_reporting.md design decision #3).
--
-- Columns:
--   client_install_id  stable per-install UUID the Deck generates (the device key)
--   user_id            reporting user from the JWT `sub`; no hard FK, matching device_history
--   device_id          arp-scan `device` row; NULL until a later device-linking step fills it
--   latitude/longitude DECIMAL(9,6) -- ~11cm resolution, far finer than the data itself
--   accuracy_m         reported horizontal accuracy in metres, or NULL
--   provider           'network' | 'gps' | 'fused' | 'last_known'
--   captured_at        device clock at fix time; reported_at is the server clock at ingest
--
-- No SA rule consumes this yet -- it is a data-collection pipeline for later use (SA-3
-- geofence departures, check_travel() origin, transition learning, location baselines). Same
-- collect-then-learn staging as attention_telemetry_history (migration 028).

CREATE TABLE IF NOT EXISTS `device_location_history` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `client_install_id` CHAR(36) NOT NULL,
    `user_id` INTEGER NOT NULL,
    `device_id` INTEGER NULL DEFAULT NULL,
    `latitude` DECIMAL(9,6) NOT NULL,
    `longitude` DECIMAL(9,6) NOT NULL,
    `accuracy_m` FLOAT NULL,
    `provider` VARCHAR(16) NULL,
    `source` VARCHAR(16) NOT NULL DEFAULT 'deck',
    `captured_at` DATETIME NOT NULL,
    `reported_at` DATETIME NOT NULL,
    INDEX `idx_dev_loc_hist_install_captured` (`client_install_id`, `captured_at`),
    INDEX `idx_dev_loc_hist_user_captured` (`user_id`, `captured_at`),
    INDEX `idx_dev_loc_hist_reported_at` (`reported_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Retention: 180 days, matching cleanup_device_history_event so downstream SA baselines see a
-- consistent window. Surfaced in the Deck PRIVACY.md.
DROP EVENT IF EXISTS `cleanup_device_location_history_event`;
DELIMITER ;;
CREATE EVENT `cleanup_device_location_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM device_location_history WHERE captured_at < DATE_SUB(NOW(), INTERVAL 180 DAY);
DELIMITER ;
