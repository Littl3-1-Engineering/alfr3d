-- Migration 032 (SA-6): geocode_cache table
--
-- Self-hosted routing (`check_travel()`) needs coordinates for a calendar event's free-text
-- `address` before it can call the routing engine. Geocoded via the public Nominatim API
-- (its usage policy caps public use at 1 request/second -- see todo/todo_self_hosted_routing.md
-- for why self-hosting Nominatim itself wasn't the right call for this pass), so every distinct
-- address is looked up at most once, ever, not once per cycle.
--
-- Keyed by address text, not by calendar_events.id: geocoding is purely a function of the
-- address string, independent of which event(s) share it, so this stays reusable outside the
-- calendar path too. A row with NULL latitude/longitude is a cached "not found" -- an
-- unresolvable address must not be re-queried every cycle either.
CREATE TABLE `geocode_cache` (
    `address` VARCHAR(256) NOT NULL PRIMARY KEY,
    `latitude` FLOAT NULL DEFAULT NULL,
    `longitude` FLOAT NULL DEFAULT NULL,
    `cached_at` DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
