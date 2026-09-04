-- Migration 035: time-of-day-aware quips
--
-- Part of tying Alfr3d's spoken lines to the household's day shape (see
-- services/common/day_context.py). Two changes:
--
--   1. "Hello sunshine" was a morning line sitting in the generic 'smart' idle
--      pool, so the daemon's unprompted "be a smartass" timer could shout it at
--      any hour. It did, at 22:00 -- and the LLM personality layer, given no
--      time context, turned it into "Good morning!". Re-typed to 'morning' so
--      only the Morning routine can say it.
--
--   2. Seed a handful of 'morning' / 'sunrise' / 'sunset' quips. util_routines
--      already referenced these types (ROUTINE_QUIP_TYPES) but no rows existed,
--      so the Morning / Sunrise / Sunset routines were silent while Bedtime
--      spoke. Idempotent: the INSERTs are skipped if a row already matches.

UPDATE `quips` SET `type` = 'morning'
 WHERE `type` = 'smart' AND `quips` = 'Hello sunshine';

INSERT INTO `quips` (`type`, `quips`)
SELECT * FROM (
    SELECT 'morning' AS t, 'Good morning. The day will not optimise itself.' AS q
    UNION ALL SELECT 'morning', 'Awake, then. I have taken the liberty of starting the day without you.'
    UNION ALL SELECT 'sunrise', 'Sunrise. Somewhere a rooster is taking credit for my work.'
    UNION ALL SELECT 'sunset', 'Sunset. The lights and I will take it from here.'
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM `quips` q WHERE q.`type` = seed.t AND q.`quips` = seed.q
);
