# Release v0.4.7

## Release Name: Second Opinion

### Notes:
- **Feature:** Nexus panel navigation is now a preference. v0.4.6 replaced the six vertical-text
  edge tabs with the HUD launcher ring around the Core outright; "nobody wants the tabs" was an
  assumption rather than a finding, so the removal becomes a choice instead — Matrix >
  Customizations > **Nexus Navigation** picks **Orbit Rings** (the default, unchanged) or
  **Edge Tabs**. Both modes drive the same panels and the same open/close state; only the
  control changes, and the choice persists per browser.
- **Feature:** A `UiPrefs` provider beside the existing theme provider, for UI preferences that
  aren't colours (`alfr3d-nexus-nav` in `localStorage`). Unrecognised or unreadable values fall
  back to the default, so a blocked store degrades to the standard look rather than to nothing.
- **Accessibility:** The restored edge tab is labelled with the bare panel title plus
  `aria-expanded`, not "Close <title>" — that name belongs to the panel's own corner close
  control, and two buttons answering to it would have been ambiguous. The corner close control
  and `Escape`, both added when the tabs were removed, stay live in **both** modes.
- **Unchanged:** the ring shape vocabulary, the state machine, and the three discipline rules
  from v0.4.6. The ring is still what ALFR3D leads with.

# Release v0.4.6

## Release Name: Heads Up

### Notes:
- **Feature:** Animated cyber HUD rings — a new `HudRing`/`HudLoading` component family
  replaces every generic spinner, "Loading..." string, and plain circular border across the
  dashboard with a shared shape+state vocabulary. Compass Ring, Split-Arc Ring, and Gear Dial
  carry real system meaning (acquire/lock, handshake/sync, process/compute); five identity
  shapes distinguish launchers and menu items; idle/working/resolve/active/fault states, with
  every ring always in motion except `fault`.
- **Feature:** Boot sequence becomes a HUD checklist — each `NexusLoader` line carries a ring
  that spins while the step runs and bounce-settles as it completes.
- **Feature:** Event stream glyphs, Core's launcher ring, Quick Controls tiles, and the
  per-routine run button in Routines all adopt the same ring vocabulary. A real bug surfaced
  along the way: Routines' `handleRun` was silently treating any non-2xx response as success.
- **Accessibility:** `prefers-reduced-motion` hard-stops all rotation; colour and the
  corner-bracket "selection" frame still carry state.
- **Design credit:** Goran Spasojevic (@gorango) — "cyber btns" CodePen, recreated from scratch
  in React/Framer Motion, not ported.

Full detail and on-device/browser verification log in
`todo/todo_cyber_hud_buttons_frontend.md`.

# Release v0.4.5

## Release Name: Diminishing Returns

### Notes:
- **Feature:** Continuous-stay guest decay — a guest who's actually moved in for a while (weeks,
  not hours) no longer reads as a fresh drop-in. Tracks each guest's current unbroken stay
  (`user.continuous_stay_since`, reset on a real 24h+ departure gap) and decays their contribution
  to both the household "energy" score and their SA cards' priority the longer they stay —
  front-loaded, crossing zero around day 14, and allowed to go negative (bounded) past that. Once
  negative, a new `guest_overstay_advisory` card nudges promoting them to resident or addressing
  the stay. RBAC/permissions are untouched — `guest` stays strictly read-only.
- **Feature:** SA-9 Phase 1 — `climate_advisory`, a fixed-threshold indoor comfort advisory read
  from the household's first accepted ESPHome temperature/humidity sensor.
- **Feature:** SA-9 Phase 2 — `climate_deviation`, a baseline-learned sibling to `climate_advisory`
  that fires on genuine deviation from what's typical for the current time of day, backed by a new
  `smarthome_sensor_history` table (730d retention) and a `time_of_day_bucket` dimension on
  `entity_baselines`.
- **Security:** Removed the dead ntfy.sh event relay from `service_api` — a legacy Tasker
  integration path that was posting household SA event data to a public, unauthenticated ntfy.sh
  topic.
- **Docs:** Restored the SA-8 BLE presence sensing todo doc (wrongly deleted by a prior cleanup)
  and re-verified it's still dead — MAC randomization defeats it structurally, confirmed again
  against the real NUC.

# Release v0.4.4

## Release Name: First Light

### Notes:
- **Fix:** ESPHome node discovery (`POST /api/iot/esphome/discover`) ran its mDNS scan inside
  `service-api`, which is on the bridge network and can never see LAN multicast traffic — it would
  silently report "0 nodes found" on any real household LAN. Now dispatches to `service-device`
  (host network mode) via Kafka, matching the original design.
- **Feature:** Manual "add by IP" fallback for onboarding an ESPHome node when mDNS discovery
  can't reach it (Wi-Fi client isolation, a VLAN, an AP that blocks multicast) — connects directly
  by IP and feeds into the same accept pipeline discovery-based onboarding uses.
- **Fix:** ESPHome sensor/binary_sensor readings were stored one shape level deeper than the
  frontend expects, crashing `ControlBlade`'s sensor panel ("Objects are not valid as a React
  child") the moment a real sensor was opened. Normalized to the same shape Home Assistant
  entities already use.
- **Fix:** A blank `"Failed to accept node: "` alert when ESPHome onboarding hit a bare
  `asyncio.TimeoutError` (its string form is empty) — falls back to the exception's type name.
- **Fix:** `service_speak`'s mute-check rename (`check_mute` → `get_mute_state`) left CI red on 6
  stale test mocks; repaired.
- **Fix:** Sunrise/Sunset/Bedtime routine quips were almost never spoken because the sleeping-hours
  gate and the routine window shared the same boundary. Sleeping and empty-house are now
  independent signals, and an empty (but not sleeping) house still emits the speak event for the
  Deck app's phone-speech relay.
- **Verified:** ESPHome's base integration (discovery, accept, poll sync) confirmed end-to-end
  against real hardware (an Athom ESP32-C3 temp/humidity sensor) for the first time since it
  shipped. Phase 5's persistent push connection remains unconfirmed against this device, traced to
  its own poor Wi-Fi link (70%+ packet loss measured directly from the NUC), not a code issue.
- **Security:** Resolved a batch of Aikido findings — CI credential persistence, Kubernetes
  non-root/capability hardening, two static-scanner false positives, a certificate-validation
  dependency floor.
- **Chore:** Dependency updates across services (aioesphomeapi, alembic, pyjwt, starlette, docker,
  uvicorn, vite, postcss, hls.js, lucide-react, @tanstack/react-query, anthropic).

# Release v0.4.3

## Release Name: Context Exchange

### Notes:
- **Feature:** Backend<->Deck context exchange protocol, phases 1-2 -- the backend's `DayContext` now flows down to the Deck launcher, and the Deck's device signals (battery/charging/DND/headset/network/foreground app) flow up, so household-awareness state and device state stop being independently re-derived on each side.
- **Feature:** `POST /api/context/notification-event` -- lets the Deck report spoken notifications back to the backend for context-aware follow-up behavior.
- **Feature:** Geofence-driven SA-12 household-events producer, plus structured `device-control` and `routine-executed` household events, feeding transition learning.
- **Feature:** Device-location reporting pipeline, backend Phase 1 (coarse, foreground-only, opt-in, per-device).
- **Feature:** `DELETE /api/iot/devices/{id}` to remove a synced smarthome device that no longer exists in Home Assistant.
- **Feature:** Scheduled 15-minute Google Calendar sync daemon.
- **Fix:** Geofence radius was smaller than the real GPS fix accuracy, causing false "left home" events.
- **Fix:** Home Assistant devices are now marked online unless HA explicitly reports them unreachable, instead of reading stale state as offline.
- **Fix:** Presence tracking no longer reads the user row by a stale index.
- **Fix:** Calendar cards render times in the household's timezone instead of UTC.
- **Fix:** The Nexus frontend renders every SA card the backend sends instead of a hardcoded cap of 9.
- **Fix:** Frontend migrated to Tailwind v4, lottie-react v3, and ESLint v9 flat config.
- **Fix:** Docker socket availability is re-checked periodically instead of only once at boot.
- **Retention:** SA event-log tables (`household_events`, `attention_telemetry_history`, `card_interactions`, `device_location_history`) retained for 2 years, moved to DB-native MySQL `EVENT`s instead of a Python delete loop, with daily growth tracking; `card_interactions` is now bounded.
- **Chore:** Dependency updates across services (alembic, pydantic, cryptography, zeroconf, autoprefixer).

# Release v0.4.2

## Release Name: Unified Day Context

### Notes:
- **Feature:** Time-of-day awareness unified behind one `DayContext` (`common/day_context.py`) -- feeds the speak mute gate, the LLM greeting prompt, arrival greetings, and the idle-quip wind-down. Fixes ALFR3D greeting "good morning" at 22:00.
- **Feature:** Nexus quick-controls panel -- up to 10 favorited smarthome devices as compact toggle/dial tiles opened from the Socket menu, with full device controls reachable from a tile.
- **Feature:** Matrix and Graphite UI themes added, alongside the existing Cyan/Navy, Amber/Charcoal, and Light/Teal themes.
- **Feature:** The owner can set a preferred form of address, surfaced in the web UI.
- **Fix:** Concurrent auth refresh calls are now deduped, stopping spurious idle logouts.
- **Fix:** Nexus quick-controls no longer shows live controls for offline smarthome devices.
- **Fix:** Personality verbal-tics and no-LLM quip substitution are now gated to roughly 1 in 8 utterances instead of firing on every speak.
- **Fix:** The speak service now recovers automatically from a hung Kafka consumer.
- **Fix:** `alfr3d.service` retries on transient boot-time `docker compose` failures instead of failing the boot outright.
- **Fix:** CI's migration-head-revision check no longer hardcodes a specific revision.
- **Fix:** The Nexus UI's version tooltip now reads the real shipped version instead of falling back to a stale hardcoded default.
- **Chore:** Dependency updates across services (cryptography, recharts, zeroconf, orjson, pymysql, anthropic, requests, aioesphomeapi, postcss-selector-parser, vite-plugin-svgr).

# Release v0.4.1

## Release Name: Real-Time ESPHome

### Notes:
- **Feature:** ESPHome Phase 5 -- persistent, auto-reconnecting `subscribe_states()` push replaces the 15-minute poll as the primary state source for accepted nodes, using aioesphomeapi's `ReconnectLogic` on a dedicated background thread. The old poll keeps running as a reconciliation fallback. Not yet exercised against a real ESPHome device.

# Release v0.4.0

## Release Name: Full Spectrum Awareness

### Notes:
- **Feature:** Self-hosted OSRM routing + leave-by travel guidance (SA-6) replacing the removed Google Maps dependency — Phase 0-2 built and live-verified against real production hardware; routing container now running.
- **Feature:** Structured card payload (SA-5) — situational-awareness cards now carry additive typed `data` fields alongside display `content`, migrated end-to-end in the backend and, in a same-day alfr3d_deck follow-up, across all 8 launcher parsers.
- **Feature:** Durable household event log (SA-11), card feedback loop & suppression (SA-1), launcher attention-telemetry history (SA-2), and calendar conferencing metadata (SA-7).
- **Feature:** Shared per-cycle context frame (SA-4) and presence-transition departure-anomaly detection (SA-3).
- **Feature:** Entity baselines generalized to per-resident/household subjects, plus two new rhythm-break-anomaly deviation types (SA-10) — live-verified, caught a real MySQL ONLY_FULL_GROUP_BY bug.
- **Investigated, correctly stopped:** SA-9 (ESPHome sensors) and SA-8 (BLE presence) at Phase 0 — no real hardware to validate against this pass. SA-12 (transition learning) stopped at Phase 0 — not enough real household_events history to mine yet.
- 19 `DISPLAY_RULES` now registered (was 16). Migrations 0027–0035.

# Release v0.3.0

## Release Name: Behavioral Signals

### Notes:
- **Feature:** Household composition awareness — a new situational-awareness card reporting which household members' claimed devices are online, with an elevated, security-relevant priority when an unclaimed/unknown device is on the network.
- **Feature:** Rhythm-break anomaly cards — a new `entity_baselines` table and scheduled job reconstruct each device's typical on/off rhythm from history, and a new check fires only on a genuine deviation from it (e.g. a light on well past its usual hours).
- **Feature:** Cross-surface continuity card — offers to pick up where you left off (paused music, an edited routine, a reported launcher session), fed by a new `POST /api/context/surface-state` endpoint and a `routines.updated_at` column. Also fixed `check_now_playing()` never persisting a play→pause transition, so pausing previously left no signal behind at all.
- **Feature:** Attention telemetry — new `POST /api/context/attention-telemetry` endpoint backing two new cards: `check_attention_focus()` (a measured, evidence-based focus signal from window-switching behavior, additive alongside the existing calendar-based `focus_needed`) and `check_wind_down_signal()` (a late-night, high-screen-time suggestion — informational only, no auto-actuation of lights/media).
- **Fix:** Self-awareness — ALFR3D's own TTS now pronounces its name "Alfred" instead of reading the leetspeak literally, and no longer announces itself coming online like a household member.
- **Refactor:** Removed the Google Maps Directions travel-guidance integration (required a paid API tier the household isn't using), replaced with a local, no-API "Open Maps" hand-off from the launcher's calendar view. See `todo_free_routing_alternatives.md` for a free/self-hosted routing replacement, not yet built.

# Release v0.2.0

## Release Name: Multi-Camera Registry

### Notes:
- **Feature:** Camera streaming now reads from the device registry instead of a single global `STREAM_CAMERA_URL` env var — any device with `device_type = 'camera'` and a `stream_url` set (via Domain → Devices) can be streamed, and the Nexus camera panel lets you select/toggle between all configured cameras.
- **Feature:** Added ESPHome as a local-only, always-on IoT provider (mDNS discovery + Noise-encrypted native API), running in parallel with whichever of Home Assistant/SmartThings is set as the default provider.
- **Fix:** Camera stream panel showing "stream unavailable"/a black rectangle — nginx's CSP had no `media-src` directive, so `blob:` URLs (used by hls.js for playback) fell back to the `default-src 'self'` policy and were blocked.
- **Security:** `stream_url` (which embeds RTSP credentials) is write-only through the API — `GET /api/devices` and its websocket broadcast only ever expose a `has_stream` boolean, never the raw URL.

# Release v0.1.8

## Release Name: Situational Awareness Registry

### Notes:
- **Feature:** Situational-awareness engine rebuilt around a rule registry (`DISPLAY_RULES` in `alfr3ddaemon.py`) instead of a fixed check list, so new card types register without hardcoding their slot.
- **Feature:** Added `mood` (ambient day/time energy read), `focus_needed` (heads-up when a call-like event is starting soon), and `weather_advisory` (forward-looking rain warning) cards.
- **Feature:** Added a `travel` card with leave-by time and estimated fuel cost for the next address-bearing calendar event, via the Google Maps Directions API; falls back to no travel card (event still shows as a plain listing) when a destination, API key, or route can't be resolved.
- **Feature:** Real OpenWeatherMap forecast integration (`get_forecast()`) backing the new rain advisory, replacing the prior stub.
- **Fix:** Card display cap now tracks the number of registered rules instead of a hardcoded slice, which previously could silently drop lower-priority cards (e.g. weather) once enough higher-priority cards fired in the same cycle. Frontend cap kept in sync with the backend registry size.

# Release v0.1.3

## Release Name: WebSockets Support

### Notes:
- **Feature:** Added WebSockets support (PR #44).
- **Security:** Updated dependencies to address security issues.
- **Dependencies:** Bumped various dependencies for improved performance and security.
