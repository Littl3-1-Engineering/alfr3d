# Centralize Home Appliance Control on the Domain/Blueprint Page

## Status: 🟡 Items 1-3 done 2026-08-24; follow-up (SmartThings generic control) fixed 2026-08-24 in `todo_smartthings_generic_control.md`

Fixed the actual bug (2026-08-24, earlier pass): `Music.jsx`'s "Cast to Speakers" section was
extracted into its own `CastToSpeakers` component and is now rendered in all three Music-tab
branches (Spotify not configured, configured-but-unauthorized, and fully authorized) instead of
only the last one — speaker volume control no longer requires Spotify auth to reach. Lint +
`npm run build` both pass. Not yet re-verified against a live authorized deployment (see README's
existing "not yet verified" notes on the Spotify/cast surfaces generally).

**Item 1 (confirm ControlBlade.jsx media_player controls are wired to the generic endpoint) —
done, and found real bugs while confirming it.** ControlBlade.jsx *is* wired to
`POST /api/iot/devices/{id}/control` (not stubbed), but three of its commands were sending
params in a shape/scale the real backend didn't expect, for both HA and ESPHome sources — wired
to the right endpoint, silently broken payload:
- `volume_set`: sent `{volume: 0-100}`; HA's `media_player.volume_set` service requires
  `volume_level` as a 0.0-1.0 float (confirmed against the known-working reference,
  `audio_cast.set_speaker_volume`, which does this correctly). ESPHome's
  `media_player_command(volume=...)` also expects a normalized 0.0-1.0 float, unlike the raw
  0-100 that was being passed straight through.
- `set_brightness`: sent `{brightness: 0-100}` (percent, per the UI slider); HA's bare
  `brightness` field on `light.turn_on` is raw 0-255, not percent — silently dimmed lights to
  ~29% of the requested level. ESPHome's brightness handler assumed the opposite (divided by 255
  as if given 0-255) so it had the identical bug from the other direction.
- `set_speed` (fan, HA only): sent `{speed: 'low'|'medium'|'high'|'off'}`; HA's
  `fan.set_percentage` service requires a numeric `percentage` field, not a speed name — this
  call would have been rejected by HA outright. ESPHome's fan handler already expected the
  `speed` name (see `_fan_speed_command`), so this was HA-only.

Fixed all five (routes/iot.py + services/common/ha_utils.py new
`translate_generic_control_params()` helper for the HA path; services/common/esphome_utils.py
for the ESPHome path). 8 new unit tests added (`tests/test_ha_utils.py`,
`tests/test_esphome_utils.py`); full suite 250/250 passing; black/flake8 clean.

**Item 3 (audit for other feature-tab-stranded controls) — done, no other instance of the
original pattern found, but a bigger adjacent gap surfaced:**
- No frontend surface besides `ControlBlade.jsx` calls a device-control endpoint. `Music.jsx`'s
  cast controls (now correctly ungated) use their own dedicated `/api/music/cast/volume` route,
  which was already parameterized correctly — not affected by the bugs above.
- The routine automation engine (`service_daemon/utils/util_routines.py`) has its own separate,
  correctly-implemented `control_iot_device()` for its action types (`thermostat_set`, `lock`,
  `unlock`, `cover_open`, `cover_close`) — doesn't touch brightness/volume/fan-speed at all, so
  it was never exposed to the bugs above and needed no fix.
- **New finding, not in scope to fix here**: SmartThings-sourced devices aren't handled by the
  generic endpoint at all — `control_iot_device()` in `routes/iot.py` only branches on
  `source == "homeassistant"` or `"esphome"`; a SmartThings device falls through to a 400
  "Unsupported source or device" on every single command. `todo_iot.md`'s Phase 5 documents this
  endpoint as the unified front door for HA **and** SmartThings, but ST support was apparently
  never added there (only the ST-specific `/iot/st/devices/{id}/control` route exists, and it
  takes raw ST `capability`/`command`/`args` rather than ControlBlade's generic vocabulary). This
  is a bigger lift than the param-scaling fixes above: ST's command model is
  capability+command+args, not domain+service, and `smarthome_devices.device_type` for ST rows
  is populated from ST's raw `deviceTypeName` label (e.g. "Samsung OCF Switch"), not the
  normalized light/switch/fan/... vocabulary `ControlBlade.jsx`'s `renderDeviceControls()`
  switches on — so ST devices likely render as the generic power-toggle fallback today regardless
  of their real capabilities, on top of every command failing outright. Needs its own scoping
  pass (device-type normalization + a capability-mapping table) rather than folding into this
  todo; flagging here since it was found during this audit.
- Also worth noting: a `media_player` device only appears on Blueprint/`ControlBlade.jsx` at all
  once it's been manually linked via `DeviceRegistry.jsx` (`Blueprint.jsx` filters to
  `iot.linked`) — so "go to the Blueprint, click the speaker" (design item 2's stated long-term
  preference) isn't zero-friction the way the Music tab's picker is, which lists every HA speaker
  directly without requiring a link step first.

## Overview

There is no single place to control every IoT/smart-home device. The Matrix "Music" tab
(`Music.jsx`) has a volume slider for cast/HA speakers, but it's gated behind Spotify authorization
even though volume control has nothing to do with Spotify — a design gap, not a deliberate
restriction. This todo proposes making the Domain/Blueprint page the one command-and-control
surface for all household appliances, using the generic IoT device control endpoint that already
exists but is under-used.

## Current State (confirmed 2026-08-23)

- **The gap**: `services/service_frontend/src/components/Music.jsx` renders a "Cast to Speakers"
  section (line 685) with a real volume slider (`<input type="range">`, lines 732-740) calling
  `setCastVolume()` (lines 304-309) → `castFetch('cast/volume', ...)` (line 308) →
  `POST /music/cast/volume` (`services/service_api/routes/music.py:512`). But that whole section is
  unreachable unless the code first passes two gates in the same component: `!auth?.configured`
  (line 324) and `auth?.configured && !auth?.authorized` (line 337) both short-circuit to a
  "connect/authorize Spotify" prompt instead of rendering the rest of the tab. A household that
  doesn't use Spotify, or hasn't authorized it, can't reach speaker volume control at all — even
  though the speakers themselves are independent HA devices with nothing to do with Spotify.
- **The infrastructure already exists to fix this without new backend work**: the generic
  `POST /api/iot/devices/{device_id}/control` (`services/service_api/routes/iot.py:455-456`,
  `control_iot_device()`) already supports a `"volume_set"` command (lines 508-509) that maps to
  Home Assistant's `volume_set` service for `source == "homeassistant"` devices (lines 475-514).
  This is the same underlying HA capability `cast/volume` calls, just reached through the
  provider-agnostic device-control route instead of a Music-tab-specific one.
- Other device-type controls (climate, lock, fan, cover, media_player) already exist server-side
  per `todo_iot.md` Phase 8, and are already surfaced through `ControlBlade.jsx` when a device is
  clicked on the Blueprint. So the Blueprint/ControlBlade pairing is already most of the way to
  being the "one place" — volume control is the specific control that's currently stranded in the
  wrong tab, not a sign that the whole control layer needs to be rebuilt.
- Provider-specific control routes also exist (`/iot/ha/devices/{entity_id}/control`,
  `/iot/st/devices/{device_id}/control`, `/iot/esphome/entities/{hostname}/{key}/control`) —
  `control_iot_device` is meant to be the unified front door over all of them per `todo_iot.md`
  Phase 5, so any device reachable from the Blueprint should already be routable generically.

## Design (sketch — needs scoping pass before implementation)

1. Make sure any `media_player`-type device (the HA speakers Music.jsx's cast controls target) is
   linked and visible on the Blueprint like any other device, so it shows up in `ControlBlade.jsx`
   with volume control — Phase 8's media_player controls in `ControlBlade.jsx` line up with this
   almost exactly; confirm they're wired to the generic `/iot/devices/{id}/control` `volume_set`
   command and not stubbed.
2. Decide whether to keep `Music.jsx`'s cast volume slider as a convenience shortcut (now
   ungated from Spotify auth) or remove it entirely in favor of "go to the Blueprint, click the
   speaker." Cutting the duplication is preferable long-term, but a quick fix (just move the
   volume section above/outside the two Spotify gates in `Music.jsx`) unblocks the actual bug
   cheaply if a full consolidation isn't wanted yet.
3. Audit the Blueprint/ControlBlade path for any other appliance-shaped control that's currently
   stranded inside a feature-specific tab the way volume control is inside Music — this todo
   started from one instance of the pattern; there may be others.

## Explicitly Out of Scope (for now)

- Rebuilding the IoT control layer itself — `todo_iot.md`'s unified `/api/iot/devices` +
  `control_iot_device` design already is the intended central control path; this todo is about
  routing the *UI* through it consistently, not replacing backend infrastructure.

## Related

- `todo_iot.md` (this directory) — the underlying unified IoT device layer (Phases 5, 8) this todo
  builds the UI consolidation on top of.
- `todo_music_spotify.md`, `todo_music.md` (this directory) — Music tab / Spotify integration work;
  this todo only touches the cast-volume section's gating, not Spotify playback itself.
- `todo_smartthings_generic_control.md` (this directory) — SmartThings devices aren't handled by
  the generic control endpoint at all; split out 2026-08-24 after this todo's item 1/3 audit found
  it (see Status above), since it's a separate, bigger scoping pass than the param-scaling bugs
  fixed here.
