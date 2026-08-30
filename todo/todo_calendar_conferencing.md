# SA-7: Sync calendar conferencing metadata

## Status: 🟡 Built 2026-08-29, not yet live-verified against a real conferencing event

Wave 1 of the situational-awareness expansion, following [[todo_household_event_log]] (SA-11),
[[todo_attention_telemetry_history]] (SA-2), and [[todo_card_feedback_loop]] (SA-1). Smallest
item on the list — converts `check_focus_needed()`'s text-only heuristic into a tiered
confirmed/probable check.

## Phase 0 findings

- `calendar_utils.sync_calendar()`'s `events().list()` call requests no `fields=` partial-
  response filter, so Google's full Event resource — including `conferenceData`/`hangoutLink`
  when an event has them — was already arriving in every sync; the code just read `summary`/
  `start`/`end`/`location`/`description` and discarded the rest. Confirmed by reading the actual
  call site, not assumed.
- `conferenceDataVersion` (the parameter the task doc flagged to verify) only gates *creating*
  conference data on write calls (insert/update/patch) — it has no effect on whether an existing
  event's `conferenceData` is returned by a read call like `list()`/`get()`. No new parameter
  needed for this read-only sync path. (Based on documented Google Calendar API behavior — there
  is no live conferencing event in the household's calendar to confirm against yet; see "Not yet
  done" below.)
- Granted OAuth scopes (`calendar.readonly`, `calendar.events.readonly`) already cover
  `conferenceData` — it's a regular field of the Event resource, not gated behind a separate
  scope. No re-consent needed for any existing user.
- Third-party (Zoom/Teams) conferencing only populates `conferenceData` when created through the
  calendar's own structured conferencing integration (an add-on, or the organizer's calendar
  system). A human pasting a Zoom link into the free-text `notes`/`address` fields by hand — a
  common case — produces nothing in `conferenceData`. This is exactly why the text heuristic in
  `focus_utils.py` is kept as a lower-confidence tier rather than retired.
- Next-free migration number confirmed as **0032** at write time (chain was at 0031 after SA-1
  landed this session).

## Phase 1 — Schema and sync

`calendar_events` gains `conference_uri` (`VARCHAR(512)`) and `conference_solution`
(`VARCHAR(64)`), both nullable (migration 0032). `calendar_utils._extract_conference_info(event)`
prefers `conferenceData`'s video entry point (`entryPoints[].uri` where
`entryPointType == "video"`, falling back to the first entry point if none is explicitly typed
"video") + `conferenceSolution.name`, falling back to the older `hangoutLink` field (labeled
"Google Meet") if `conferenceData` is absent. `sync_calendar()` persists both columns on every
INSERT; `get_upcoming_events()`'s SELECT and returned dict include them too. SA-11's calendar
event-stream diff (`row_key`) deliberately excludes these two fields — a conference link
appearing on an otherwise-unchanged event isn't a new household event worth republishing.

## Phase 2 — Layered detection

`focus_utils.looks_like_call(address, notes, conference_uri=None)` now returns one of three
values instead of a bool: `CONFIRMED` ("confirmed") when `conference_uri` is present (regardless
of what the text says), `PROBABLE` ("probable") when only the text heuristic matches, or `None`
when neither fires. The documented false-positive case ("re-zoom the picture before the
meeting") still fires — that's an accepted limitation of tier 2 the task doc explicitly says not
to try to fix — but can now never be promoted to `CONFIRMED` on text content alone; only a real
synced `conference_uri` reaches that tier.

`check_focus_needed()`'s card gained `confidence` (`"confirmed"`/`"probable"`) and
`conference_uri` (nullable, for a future Phase 3 "Join" action) fields, and its content copy is
now calibrated: `"{conference_solution or 'Call'} starting soon: {title}..."` when confirmed vs.
`"Looks like a call starting soon: {title}..."` when only probable. `focus_utils.py`'s module
docstring rewritten to describe the tiered detector it now actually is, rather than the v1 it
described before.

30 new/changed daemon tests: `TestExtractConferenceInfo` (video-entry preference, hangoutLink
fallback, no-conference-data cases), `TestFocusUtils` (all six existing assertions updated for
the string-tier return value, plus 3 new: confirmed-regardless-of-text, the false-positive
staying at probable, no-conference-uri fallback), `TestCheckFocusNeeded` (confirmed-tier card
content/fields, the false-positive-fires-but-only-probable acceptance criterion, a
pre-migration/null-fields case), and `TestCalendarSync` (conference metadata persisted when
present, NULLs persisted when absent).

## Not yet done

- **Live verification against a real conferencing event.** The household's current calendar
  data (seen during SA-11's live verification) has no event with structured `conferenceData` —
  everything so far is a plain event with no conferencing. The Google API behavior this whole
  phase depends on (read calls returning `conferenceData` with no extra scope/parameter) is
  based on documented behavior, not confirmed against this household's own real sync yet.
  Next real Google Meet/Zoom-integrated invite synced should be checked directly:
  `SELECT conference_uri, conference_solution FROM calendar_events WHERE conference_uri IS NOT
  NULL`.
- **Phase 3 (Join action)** — explicitly out of scope for this pass per the task doc; flagged,
  not built. `conference_uri` is already on the card, ready for a future launcher/dashboard
  "Join" button.
- Frontend (`SituationalAwareness.jsx`) wasn't touched — the new `confidence`/`conference_uri`
  card fields are additive and the existing generic card renderer already displays `content`
  unchanged regardless of what extra fields a card carries; no UI change was needed for this
  phase specifically (Join UI is the deferred Phase 3).

## Out of scope (per the task doc, unchanged)

- Join actions in any UI (Phase 3, separate).
- Non-Google calendar providers.
- Any change to `check_attention_focus()` — the evidence-based sibling, deliberately independent.
