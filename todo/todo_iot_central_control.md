# Centralize Home Appliance Control on the Domain/Blueprint Page

## Status: 🟡 Quick fix shipped 2026-08-24 (design item 2); items 1 and 3 still open

Fixed the actual bug: `Music.jsx`'s "Cast to Speakers" section was extracted
into its own `CastToSpeakers` component and is now rendered in all three
Music-tab branches (Spotify not configured, configured-but-unauthorized, and
fully authorized) instead of only the last one — speaker volume control no
longer requires Spotify auth to reach. Lint + `npm run build` both pass. Not
yet re-verified against a live authorized deployment (see README's existing
"not yet verified" notes on the Spotify/cast surfaces generally).

Design items 1 (confirm `ControlBlade.jsx` media_player controls are wired
to the generic endpoint) and 3 (audit for other feature-tab-stranded
controls) are unstarted — this pass only did the quick fix (item 2's second
option: move the section out from behind the gates, implemented by
rendering the extracted component unconditionally rather than duplicating
the JSX). Full consolidation onto Blueprint/ControlBlade, if wanted, is
still a separate scoping pass.

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
