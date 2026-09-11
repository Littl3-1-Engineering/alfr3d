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
- **SA-12** (`todo_transition_learning.md`, still stopped — Phase 0b re-check 2026-09-07): elapsed
  time is no longer the blocker (`household_events` now spans ~9 real days). The blocker is
  structural — the candidate transition pairs (presence→device, routine→device, device→device)
  had **zero** structured rows because no producer emitted them. Branch C fix shipped (commit
  `b9e6e36f`): `service_api` now emits structured `device/turned_*` and `routine/executed`
  events. SA-12 stays stopped; **re-check ~2026-09-28** once those two new streams have real
  history. `device/*` events are near-zero and will stay that way: HA itself is healthy and
  syncing (`192.168.2.200:8123`, up since Aug 29), but ~59 of 61 HA entities are `unavailable`
  because **the household moved** — the Google Home speakers / TVs / tablets stayed at the old
  place. Only `Moonrise TV` (+`moonrise_tv_2`) followed. Some of the rest *may* be recovered,
  so removal is deliberate, not automatic: Athos will delete the gone-for-good ones (in the HA
  UI, then `DELETE /api/iot/devices/{id}` — new endpoint, commit `3dfa3f29` — clears the alfr3d
  row + its command history; the earlier auto-prune `3b10fadb` was reverted as too aggressive
  and FK-unsafe). Net for SA-12: the device-transition stream has ~one controllable device
  until the new house accumulates real smart devices — structurally thin, SA-12 stays stopped.
- **SA-9** (`todo_esphome_situational_awareness.md`, stopped at Phase 0): revisit only if the
  household actually gets a real ESPHome node (a live mDNS scan of the real LAN found none as of
  2026-08-30).
- **SA-8** (`todo_ble_presence_sensing.md`, dead at Phase 0): revisit only if a BLE
  wearable/tracker with a genuinely stable, resolvable address enters the household — the
  adapter itself is confirmed capable, the problem was zero stably-identifiable personal devices
  in the real scan.

**Could just be done, no permission needed, just wasn't finished:**
- **SA-9/SA-8's stopped conditions**: both could be retried in a differently-configured
  environment (faster network for an ESPHome host-mode virtual device; a real BLE wearable in
  hand) without needing new code — see each doc's own "Not yet done" section for the concrete
  retry conditions.

**All pushed and released as of 2026-09-01 — nothing outstanding here:**
- **`alfr3d`**: v0.4.0/v0.4.1 plus the 2026-08-31 hardening batch (hung-Kafka-consumer recovery,
  version-string desync fix, offline-device control gating, auth refresh dedupe, CI migration-head
  fix, systemd retry) — all committed, pushed, working tree clean.
- **`alfr3d_deck`**: 0.1.34, and the now-redundant regex fallback in `MusicEnergy` **has been
  deleted** (commit `1f301dd`, "refactor(context): remove regex fallback in MusicEnergy parsing")
  now that the structured `data.energy`/`data.genre` path is confirmed live on-device. Working
  tree clean.

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
- **2026-08-30 (later)**: found both `alfr3d` and `alfr3d_deck` already committed/released
  (0.4.0 and 0.1.34) and clean — the "uncommitted" note above is stale, superseded by an
  intervening commit. With adb access to a real device (wireless, over Tailscale), verified
  `alfr3d_deck`'s structured-`data` path (SA-5) on-device against the live backend; the regex
  fallback in `MusicEnergy` was then deleted (commit `1f301dd`). SA-5 is fully closed — its
  `todo_structured_card_payload.md` was removed in the 2026-09-01 cleanup.
- **2026-08-31**: `alfr3d` hardening session (not SA-roadmap) — six fix commits landed and were
  pushed: `de9d74e9` Nexus quick-controls pane for favorite IoT devices (+ `cd8253e4` README),
  `bda4922b` auth refresh-call dedupe (spurious idle logout), `595df241` VERSION-file desync /
  stale hardcoded version in the Nexus UI, `83c0ad40` hide live controls for offline smarthome
  devices, `b8463ed4` CI stop hardcoding the migration head revision, `a9763c3d` systemd retry on
  transient boot-time compose failures, `651454e7` recover from a hung service-speak Kafka
  consumer (~44h silent outage) + gate LLM verbal tics to ~1 in 8.
- **2026-09-01**: todo cleanup pass. Closed the last two buildable open items — the personality
  verbal-tic/quip overuse (LLM path fixed in `651454e7`; added matching ~1-in-8 gating to the
  no-LLM quip-substitution path in `service_speak/app.py` with tests) and the two extra UI
  themes `matrix` + `graphite` (theme-CSS generator generalized to iterate all themes). Then
  synced the Notion **Alfr3d Timeline** and **deleted 24 fully-completed todo docs** across the
  three repos (all recoverable from git history) — every remaining `todo/` file here is either a
  reference doc or has a genuine blocker (real-world event, real hardware, paid Aikido plan, or
  pending on-device verification). Deleted from `alfr3d/todo/`: implementation_plan,
  optimizations, optimizations_v2, personality, todo_customizations, todo_branch_naming_consistency,
  todo_container_autostart, todo_db_schema_diagram, todo_encrypt_secrets_at_rest,
  todo_flask_to_fastapi, todo_onboarding_first_user, todo_routines, todo_theme_centralization,
  todo_websockets, tree_of_alfr3d, todo_music_playlist_recommendation, todo_structured_card_payload,
  todo_ble_presence_sensing, todo_email_service, todo_free_routing_alternatives. Plus deck's
  app_drawer_cache / auth_rbac / launcher_rotation_lock and littl31's mobile_scramble_jitter.

- **2026-09-04**: shipped **DayContext** (commit `3fa2f072`, alembic 0037) — unified time-of-day
  source feeding the mute gate, LLM prompt, greeting, and idle-quip wind-down; fixes "good
  morning at 22:00". Deployed. Not an SA-roadmap item; tracked in `todo_day_context.md`-adjacent
  work / memory.
- **2026-09-07**: owner can set a preferred form of address (`service_speak`, commits `12a77fdf`
  + `f35e23fe` web UI). Also fixed a real presence-tracking bug — `service_user` was reading the
  user row by a stale positional index (`f9abf62c`).
- **2026-09-08**: **SA-12** picked back up for a Phase 0b re-check — see the revised SA-12 bullet
  above. Verdict: still stopped, but the *reason* changed (structural, not time), and the two
  missing structured-event producers were built and deployed (`b9e6e36f`). Concrete re-check
  date: ~2026-09-28.
- **2026-09-08**: `littl31` CI workflow added (`.github/workflows/ci.yml` — build + pre-commit),
  closing the last non-Aikido item in `todo_repo_standardization.md`. `alfr3d_deck` shipped a
  large batch this week outside this repo's roadmap (Deck/Socket rename, AGP 9 upgrade,
  first-launch onboarding, app long-press menu, app-list disk cache on a branch) — see that
  repo's `todo/` and `agents.md`.
- **2026-09-08**: verified the household HA instance is healthy (`192.168.2.200:8123`, running
  since Aug 29, `GET /api/iot/ha/status` → `connected`, weather/battery sensors fresh today).
  Found + fixed a real bug this un-masked (commit `93354114`): `sync_ha_devices()` set
  `online = state == "on"`, so any reachable HA device not in state `on` (media_player on
  `idle`, an off light, a `locked` lock, a `heat`ing climate unit, every sensor) was marked
  offline and hidden by the launcher. Now `online` = "HA isn't reporting `unavailable`/
  `unknown`". **Then the household clarified: the ~59 dead devices are a house move** — the
  Google Homes / TVs / tablets stayed at the old place; only Moonrise TV followed, and some of
  the rest *may* be recovered. First tried an auto-prune in `sync_ha_devices()` (`3b10fadb`),
  then **reverted it** (`85e6be17`) — destroying a device that drops off for a day mid-recovery
  is wrong, and the DELETE was FK-unsafe (`device_command_history` has no cascade). Replaced
  with an explicit `DELETE /api/iot/devices/{id}` endpoint (`3dfa3f29`, technoking-only, clears
  command history then the row). Athos will delete the gone-for-good devices in HA + via that
  endpoint (auto-prune was offered and declined — leave it manual). **Deployed to the NUC
  2026-09-08** (`service-api` + `service-device` rebuilt, no migration); post-deploy sync moved
  `online` 1→44, only the ~17 genuinely `unavailable`/`unknown` entities stay hidden.

- **2026-09-11**: built the geofence → SA-12 `household_events` producer that
  `todo_device_location_reporting.md`'s "Deferred" section named (`user`/`left_area`|
  `entered_area`, `_emit_geofence_transition_events()` in `routes/context.py`, wired into
  `POST /api/context/device-location`). Backend-side distance-from-home check against the
  existing coarse/foreground-only location pipeline, not real OS geofencing — stays inside
  that feature's no-background-location-permission design decision. 14 new unit tests, full
  suite green (536 passed), black/flake8 clean. Committed (`e85b4b4d` feat, `567ee98a` docs),
  pushed to `origin/main`, and **deployed to the NUC** the same day: `git pull --ff-only`
  (confirmed the only non-doc commits in the fast-forward were this feature's own), `docker
  compose build service-api` + `docker compose up -d service-api`, verified clean startup
  (real dashboard/daemon traffic flowing, no import errors) and that
  `_emit_geofence_transition_events` imports fine inside the running container. Deliberately
  did **not** inject synthetic location data into production to test the geofence logic
  end-to-end.

- **2026-09-11 (later, same day)**: checked `household_events` for a real crossing — zero
  rows, but the raw `device_location_history` already had a genuine ~13.6km trip in it from
  earlier that day. That's a real bug, not "hasn't happened yet": the shipped 300m radius was
  smaller than the ~2000m accuracy `todo_device_location_reporting.md`'s own Phase 0 already
  documented coarse-location fixes get clamped to, making "home" structurally unreachable — so
  no baseline, so no transition, ever, regardless of real travel distance. Fixed
  `_HOME_GEOFENCE_RADIUS_M` 300→3000m (matching that doc's own "~3km" recommendation, missed
  on the first pass) and, since the fix also exposed that the baseline lookup only checked the
  single most recent prior fix (itself often ambiguous at this accuracy), changed it to walk
  back up to 20 prior fixes for the last confidently-classified one. Re-verified against the
  same real production fixes (not mocks): now correctly resolves one `left_area` transition.
  1 new test, 68 total, all green; redeployed to the NUC same day. See
  `todo_transition_learning.md`'s "First real-data check" section for the full writeup. Still
  zero rows in `household_events` — the fix doesn't retroactively backfill events for fixes
  already stored before the fix landed; needs a fresh crossing to produce a live row.

*(Add a dated entry here each time one of the above gets picked up, so this doc doesn't silently
go stale the way the README/Notion pages did before this session's cleanup pass.)*
