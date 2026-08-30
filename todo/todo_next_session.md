# Next session: where the SA roadmap stands

## Status: reference doc, not a task — updated 2026-08-30 after the full deployment pass

Everything in this doc is a pointer, not new information — each item links to its own
`todo/todo_*.md` for the real detail. Purpose: let a future session (or a human) pick up without
re-reading fifteen separate docs first. Update this doc's own "Since this was written" section
whenever picking one of these back up, rather than editing history above it.

## Everything is live in production

All of Wave 1–4's code (SA-11, SA-1, SA-2, SA-7, SA-4, SA-5 backend, SA-3, SA-6 backend/schema,
SA-10) is deployed to the household's real NUC as of 2026-08-30 — merged to `main` via PR #156,
migrated (0026→0035), rebuilt, redeployed, and verified live. A real `mysqldump` backup was taken
first (`~/db_backups/alfr3d_backup_20260830_024427.sql` on the NUC). See each item's own
`todo/todo_*.md` for the "Deployed to production" note.

## Open items, grouped by what they need

**Waiting on a real-world event — nothing to build, just time:**
- **SA-3** (`todo_departure_anomaly.md`): `check_departure_anomaly()` has never fired live. Needs
  a resident whose baseline clears both reliability gates (currently only `athos`/weekend) to
  actually be away past their typical hour with no calendar event covering it. Now running
  against real production history, not the local dev stack's mirrored copy — check back.
- **SA-10** (`todo_generalize_entity_baselines.md`): `expected_absent` and
  `household_unusual_day` have never fired live either, same reasoning — needs a genuine
  deviation day to occur.
- **SA-7** (`todo_calendar_conferencing.md`): the tiered confirmed/probable conferencing
  detection has never seen a real event with structured `conferenceData` from Google. Check
  `SELECT conference_uri, conference_solution FROM calendar_events WHERE conference_uri IS NOT
  NULL` next time a Meet/Zoom invite syncs.
- **SA-12** (`todo_transition_learning.md`, stopped at Phase 0): `household_events` had ~10 hours
  of real history and 71 structured rows when checked. Re-run the Phase 0 check
  (`SELECT COUNT(*), MIN(occurred_at), MAX(occurred_at) FROM household_events`) after it's had
  real weeks to accumulate, and only then reconsider building `event_transitions`.
- **SA-9** (`todo_esphome_situational_awareness.md`, stopped at Phase 0): revisit only if the
  household actually gets a real ESPHome node (a live mDNS scan of the real LAN found none as of
  2026-08-30).
- **SA-8** (`todo_ble_presence_sensing.md`, dead at Phase 0): revisit only if a BLE
  wearable/tracker with a genuinely stable, resolvable address enters the household — the
  adapter itself is confirmed capable, the problem was zero stably-identifiable personal devices
  in the real scan.

**Could just be done, no permission needed, just wasn't finished:**
- **`alfr3d_deck` (SA-5 Phase 2 + SA-6 Phase 3, same-day follow-up)**: the Kotlin structured-`data`
  migration (`MusicEnergy.parseAlfr3dSignal()` reading `data.energy`/`data.genre` structurally),
  SA-6 Phase 3 (`next_event_soon` now reads the real `travel` card and shows the computed
  leave-by time instead of the plain "Open Maps" hand-off), and migrating the other 7
  `SituationalInsights.kt` parsers to read `data` structurally are all now done — but all still
  exist only in that repo's own working tree, **uncommitted**. `./gradlew :app:assembleDebug`,
  `ktlintCheck`, and `detekt` all pass clean; never verified on-device (no device/emulator
  available in this environment all session). Commit it when ready — see `alfr3d_deck/agents.md`'s
  2026-08-30 entries for the full detail (two entries: the original SA-5 Phase 2 pass, and the
  same-day "SA-6 Phase 3 ... SA-5 Phase 2's remaining 7 parsers migrated" follow-up).
- **SA-9/SA-8's stopped conditions**: both could be retried in a differently-configured
  environment (faster network for an ESPHome host-mode virtual device; a real BLE wearable in
  hand) without needing new code — see each doc's own "Not yet done" section for the concrete
  retry conditions.

## Since this was written

- **2026-08-30**: SA-6's `routing` container started on the production NUC with explicit
  go-ahead. Found and fixed a real bug in `setup/build_routing_extract.sh`'s copy step (the
  prior session's chmod "fix" never actually worked — `docker run` doesn't invoke a shell, so the
  glob never expanded). Container is live (`restart: unless-stopped`), and the full runtime path
  is verified end-to-end via the actual `get_route()` code from inside the deployed
  `service-daemon` container — see `todo_self_hosted_routing.md` for detail. `check_travel()`
  itself just needs a real calendar event with an address to fire; that's the only remaining
  "not yet done" item and it's a waiting-on-real-world-event, not a build task.
- **2026-08-30**: picked up the `alfr3d_deck` "could just be done" bullet's three items (Kotlin
  structured-`data` migration, SA-6 Phase 3, remaining-7-parser migration) — all done, all still
  uncommitted in that repo's working tree. See `alfr3d_deck/agents.md`'s same-day follow-up entry.

*(Add a dated entry here each time one of the above gets picked up, so this doc doesn't silently
go stale the way the README/Notion pages did before this session's cleanup pass.)*
