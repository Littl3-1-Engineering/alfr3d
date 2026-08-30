-- Migration 030 (SA-7): calendar conferencing metadata
--
-- Google Calendar's events().list() response already includes `conferenceData` (the modern,
-- general field: covers Google Meet, Zoom, Teams, phone/SIP entry points via
-- conferenceSolution.name + entryPoints[].uri) and the older `hangoutLink` (Google Meet only)
-- for any event that has structured conferencing attached -- no extra `conferenceDataVersion`
-- parameter or broader OAuth scope is needed to *read* it (that parameter only gates *creating*
-- conference data on write calls); `calendar_utils.py` was just discarding both fields after
-- fetching them. Nullable and backwards-compatible: events synced before this migration, or an
-- event with no structured conferencing (a Zoom link pasted into notes by hand, say), simply
-- have nulls here and fall through to focus_utils.looks_like_call()'s existing text heuristic.
ALTER TABLE `calendar_events`
    ADD COLUMN `conference_uri` VARCHAR(512) NULL DEFAULT NULL AFTER `notes`,
    ADD COLUMN `conference_solution` VARCHAR(64) NULL DEFAULT NULL AFTER `conference_uri`;
