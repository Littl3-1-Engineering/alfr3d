-- Migration 055: card_interactions learns two explicit feedback actions
--
--   acked        the checkmark ("got it"): acknowledges and clears the card, a mild positive
--   not_useful   the only clearly negative action; an optional reason goes in `detail`
--                (wrong_time | already_knew | not_relevant | other)
--
-- `dismissed` stays as it was and now means a swipe-away: "seen, no comment" (neutral). Old rows
-- are not remapped. Suppression (service_sa) treats acked and dismissed as the 60-minute
-- cooldown and not_useful as a long one; urgent cards are never suppressed whatever is reported.
ALTER TABLE `card_interactions`
  MODIFY COLUMN `action`
    ENUM('shown', 'tapped', 'dismissed', 'expired', 'impression', 'acked', 'not_useful') NOT NULL;
