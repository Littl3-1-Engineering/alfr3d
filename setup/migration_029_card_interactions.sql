-- Migration 029 (SA-1): card_interactions table
--
-- Card identity is (rule_id, subject_key), not (mode, content_hash) as first floated:
-- 1. The card's own "mode" field collides across rules -- check_gatherings() (rule id "music")
--    and check_now_playing() (rule id "now_playing") both stamp "mode": "music" on their card.
--    DISPLAY_RULES' own rule id is the thing that's actually unique per check, so that's what
--    identifies a card here, not its content's "mode" field.
-- 2. A pure content hash fragments identity for anything whose content legitimately changes
--    every cycle without being a "new" thing worth separate suppression state -- now_playing's
--    content changes every track; dismissing "now playing" should mean "stop telling me what's
--    playing for a while", not "I've seen this exact track's card before". So most rules use
--    rule_id alone as their identity (singleton -- there's only one "now playing" card slot to
--    suppress, regardless of which track). Only rules that can legitimately recur for different
--    underlying entities get a real subject_key: rhythm_break_anomaly (a specific device is
--    overdue) and cross_surface_continuity (a specific session to resume) -- dismissing one
--    device's overdue-anomaly card must not suppress a different device's.
CREATE TABLE `card_interactions` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `rule_id` VARCHAR(64) NOT NULL,
    `subject_key` VARCHAR(255) NOT NULL DEFAULT '',
    `action` ENUM('shown', 'tapped', 'dismissed', 'expired') NOT NULL,
    `user_id` INT NULL DEFAULT NULL,
    `occurred_at` DATETIME NOT NULL,
    INDEX `idx_card_interactions_identity_occurred` (`rule_id`, `subject_key`, `occurred_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
