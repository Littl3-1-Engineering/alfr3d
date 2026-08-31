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
