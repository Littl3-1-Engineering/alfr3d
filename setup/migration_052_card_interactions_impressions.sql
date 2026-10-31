-- Migration 052: card_interactions learns what an impression is
--
-- `shown` is reported every backend refresh by every surface (web and Deck both), so 110,000 rows
-- in 8.5 weeks collapse to ~900 real display episodes, and nothing says which surface or for how
-- long. This adds what a learner needs, all optional so older clients keep working:
--   surface        'web' | 'deck'
--   impression_id  one id per card display, shared by that display's shown/tapped/dismissed rows
--   visible_ms     how long the card was on screen; carried by the new `impression` action,
--                  sent once when the display ends
--   detail         what a tap opened (<= 64 chars)
-- Rows with action = 'impression' are invisible to decide_displays()'s suppression pass (it reads
-- shown/tapped/dismissed only).
ALTER TABLE `card_interactions`
  MODIFY COLUMN `action` ENUM('shown', 'tapped', 'dismissed', 'expired', 'impression') NOT NULL,
  ADD COLUMN `surface` VARCHAR(16) NULL DEFAULT NULL AFTER `user_id`,
  ADD COLUMN `impression_id` VARCHAR(36) NULL DEFAULT NULL AFTER `surface`,
  ADD COLUMN `visible_ms` INT UNSIGNED NULL DEFAULT NULL AFTER `impression_id`,
  ADD COLUMN `detail` VARCHAR(64) NULL DEFAULT NULL AFTER `visible_ms`,
  ADD INDEX `idx_card_interactions_impression` (`impression_id`);
