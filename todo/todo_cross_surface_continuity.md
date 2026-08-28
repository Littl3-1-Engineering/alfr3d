# Deck: Cross-Surface Continuity Card

## Status: ✅ Built 2026-08-28 (not yet on-device/live verified)

Backend: migration `0026_routines_updated_at.py` adds `routines.updated_at` (`ON UPDATE
CURRENT_TIMESTAMP`, zero application-code changes needed). New route
`services/service_api/routes/context.py`: `POST /api/context/surface-state`
(technoking/resident only, new `"context"` entry in `auth/permissions.py`'s matrix), upserts
`SURFACE_STATE_CONFIG_KEY` in `config`. `check_now_playing()` was changed so a play->pause
transition now persists too (previously it only ever wrote on an *active* playing state, so a
paused track left no signal at all to read back -- see its own docstring addition). Read side
(`_read_now_playing_config`/`_write_now_playing_config`) generalized to `_read_config_json(key)`,
reused for both `NOW_PLAYING_CONFIG_KEY` and `SURFACE_STATE_CONFIG_KEY`, per this doc's own
"factor into a shared helper" note. `MyDaemon.check_cross_surface_continuity()` picks the most
recent surviving candidate across all three sources, each discarded past
`CROSS_SURFACE_STALENESS_MINUTES` (45). 5 new daemon tests + 1 new pause-persistence regression
test on `check_now_playing()` + 3 new API route tests (401/403/200-with-upsert). Deck:
`CrossSurfaceContinuityInsight` + `cross_surface_continuity` `ContextRule` (Atmosphere tier,
priority 10, verbatim content, informational only -- no wired "Resume" action yet, see Design
below); `Alfr3dClient.reportSurfaceState()` + `HttpAlfr3dClient` impl; `WindowManager.openWindow()`
and `.focus()` both report surface state best-effort, using each window's existing `layoutKey` as
`active_surface` and `layoutKey == "terminal"` as the terminal-session signal. Compiles clean,
ktlint/detekt clean.

Not built: the actual "Resume" deep-link action (reopen/focus the relevant window from the card)
-- today's card is informational only, per the Design section below.

---

## Status: 🔲 Not started (historical, see above)

## Overview

Already-tracked state (Spotify playback/casting target, last-edited Matrix routine, an open
terminal session) currently isn't surfaced across surfaces. Offer a "pick up where you left off"
card — resume paused kitchen playback, reopen the last-edited routine, restore a terminal
session. Scoped in Notion 2026-08-28, described there as the most "butler-ish" of the five new
Deck data features: picking up what you set down rather than reading a new sensor. No new
external data source — cross-referencing state ALFR3D already holds, plus one new signal
(active Deck surface) the launcher needs to start reporting.

## Design

### Schema
- Migration `setup/migrations/versions/0026_routines_updated_at.py`: add
  `routines.updated_at TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP`. Gives
  "last-edited routine" for free — MySQL bumps it on any `UPDATE routines ...` with zero
  application-code changes to the existing routine-editing routes.
- No new table for surface state — reuse the `config` table's existing generic key/value
  pattern (same one `NOW_PLAYING_CONFIG_KEY` already uses in `alfr3ddaemon.py`), under a new
  `SURFACE_STATE_CONFIG_KEY`.

### New backend write path (Deck → backend)
- New route file `services/service_api/routes/context.py` (new, single-purpose, matching the
  one-file-per-domain convention of `music.py`/`iot.py`): `POST /api/context/surface-state`,
  auth-required (same dependency pattern as `music.py`'s POST routes). Body:
  `{active_surface: str, terminal_session_active: bool}`. Writes
  `{active_surface, terminal_session_active, updated_at}` as JSON into `config` under
  `SURFACE_STATE_CONFIG_KEY`, reusing the read/write-config-JSON helper pattern already
  established by `_read_now_playing_config()`/`_write_now_playing_config()` in
  `alfr3ddaemon.py` (factor those into a shared `config_json.py`-style helper if reused a third
  time; for now, mirror the pattern rather than duplicate it verbatim).

### Continuity check
- New `MyDaemon.check_cross_surface_continuity()` DISPLAY_RULES method reads three sources and
  offers the most recent one:
  1. Last-paused Spotify state — existing `NOW_PLAYING_CONFIG_KEY` config entry, filtered to
     `play_state == "paused"`.
  2. Most-recently-edited routine — `SELECT * FROM routines ORDER BY updated_at DESC LIMIT 1`.
  3. Last-reported terminal session — `SURFACE_STATE_CONFIG_KEY` config entry.
  Picks whichever has the most recent timestamp. Priority `5.5` (helpful, below `weather`,
  above `mood` — not urgent, a convenience offer). Card shape: `{"mode":
  "cross_surface_continuity", "content": str, "priority": 5.5, "resume_type": "music" |
  "routine" | "terminal", "resume_target": str}`.
- Register in `DISPLAY_RULES`.

### Deck
- `alfr3d_deck`: new `suspend fun reportSurfaceState(...)` on `Alfr3dClient`/
  `HttpAlfr3dClient.kt`, using the existing `requestWithBody(path, method, jsonBody)` helper
  (same pattern as `controlIotDevice`).
- `window/state/WindowManager.kt`: call the new report from `focus(id)` — the existing hook that
  already fires whenever a window becomes active — resolving the focused window's type to an
  `active_surface` string. The terminal window's open/foreground path sets
  `terminal_session_active = true` the same way.
- New insight type for `mode == "cross_surface_continuity"` in
  `contextawareness/SituationalInsights.kt`, registered in `ContextRules.kt`. Card includes a
  "Resume" action wired back into `WindowManager.openWindow`/`focus` based on
  `resume_type`/`resume_target` — no new window-opening mechanism needed, reuses what's there.

## Open questions

- Whether "last-edited routine" should exclude routines edited by the request that's asking for
  the continuity card itself (avoid a resume-offer immediately after someone finishes editing a
  routine, which isn't really "picking up where you left off").
- Debounce/expiry: a paused track from 6 hours ago probably shouldn't still trigger a resume
  offer. Needs a max-staleness cutoff per source (exact windows TBD, likely tens of minutes for
  music, longer for routines/terminal).

## Related

- `todo_music_spotify.md` — owns the existing now-playing config entry this feature reads.
- `todo_routines.md` — owns the routines table/editing routes this feature reads from.
