-- Migration 034: device_favorites table
--
-- Backs the Nexus "quick controls" pane (click the Core to open a top-center panel
-- with up to 10 favorited smarthome_devices toggles/dials). Favorites are per-user
-- rather than global -- each household member curates their own quick-access set.
-- `position` orders the favorites list for stable, predictable tile placement.
CREATE TABLE `device_favorites` (
  `id` INTEGER UNSIGNED AUTO_INCREMENT,
  `user_id` INTEGER NOT NULL,
  `smarthome_device_id` INTEGER NOT NULL,
  `position` INTEGER NOT NULL DEFAULT 0,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_user_favorite_device` (`user_id`, `smarthome_device_id`),
  INDEX `idx_device_favorites_user_position` (`user_id`, `position`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `device_favorites` ADD CONSTRAINT `fk_device_favorites_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
ALTER TABLE `device_favorites` ADD CONSTRAINT `fk_device_favorites_device` FOREIGN KEY (`smarthome_device_id`) REFERENCES `smarthome_devices` (`id`) ON DELETE CASCADE;
