# Deck: Attention Telemetry as a Focus/Wind-Down Signal

## Status: ✅ Built 2026-08-28 (scope corrected, reconciled, not yet on-device/live verified)

Backend: `POST /api/context/attention-telemetry` (routes/context.py, shares the new
`_upsert_config_json` helper with `surface-state`), `check_attention_focus()` and
`check_wind_down_signal()` DISPLAY_RULES checks in `alfr3ddaemon.py`, both reading a shared
`_read_fresh_attention_telemetry()`/`_media_dwell_fraction()` pair. 13 new tests (3 API route,
10 daemon). Deck: `AttentionTelemetryStore` (in-memory rolling-window accumulator — deviated from
the plan's "DataStore-backed" assumption once it was clear persistence across process death
isn't needed for a 15-minute rolling window), `AttentionTelemetryReporter` (own 15-min timer,
started from `MainActivity`'s existing init `LaunchedEffect`), a new `MainActivity.onResume()`
override for unlock detection, `WindowManager.openWindow()`/`.focus()` both call
`recordWindowFocus()` alongside the surface-state report already there, two new
`SituationalInsights`/`ContextRules` entries. Compiles clean, ktlint/detekt clean.

Thresholds (`ATTENTION_FOCUS_MIN_SWITCHES`, `WIND_DOWN_MIN_UNLOCKS`, media-dwell fractions) are
conservative starting points with no real telemetry yet to tune them against — same caveat as
`check_rhythm_break_anomaly()`.

## Correction to the original scope (2026-08-28)

The original Notion milestone said Nexus Launcher "already tracks unlock frequency, per-app-
category dwell time, and window-switch rate... but doesn't publish it." **That's false** —
verified by grepping the whole `alfr3d_deck` codebase: nothing tracks unlock frequency or
window-switch rate anywhere, and the only "dwell" hits are the Nexus radial menu's
hover-to-open-submenu haptic (`NexusViewModel.kt`), unrelated to usage analytics.
`search/usage/AppUsageStore.kt` (the closest existing thing) only tracks launch count +
last-used timestamp per app for search ranking, not duration or switching. This todo is
therefore building three on-device tracking mechanisms from scratch and then publishing them —
materially bigger than "wire up an existing signal," confirmed with the user before proceeding.

## Reconciliation with "Explore: Nexus Launcher as a new context source" (resolved, no longer a
blocker)

That page's "DND correlation with `focus_needed`" is a different, simpler signal (the device's
current Do-Not-Disturb toggle) than attention telemetry's continuous behavioral metrics
(unlock/dwell/switch-rate). They're complementary, not competing: DND-correlation isn't built
(still just a brainstormed line on that page, no todo doc of its own), so attention telemetry
adds its own new, clearly-named card (`mode: "attention_focus"`) rather than touching
`check_focus_needed()` at all. A future DND-based signal can combine with it later (e.g. an OR of
both) without either needing to change.

## Design

### Deviations from the original scope
1. **No literal new Kafka topic.** Every Deck→backend integration in this codebase goes through
   REST (`HttpAlfr3dClient` → `service_api` routes) -- the Deck never touches Kafka directly.
   New endpoint `POST /api/context/attention-telemetry`, same shape as
   `POST /api/context/surface-state`.
2. **No per-signal opt-in toggle UI.** No existing precedent anywhere in Settings, and
   `AppUsageStore` (closest analog) has never had one either. Explicitly deferred, separable
   future scope -- not silently skipped.
3. **Derived from the launcher's own window system, not Android usage-stats permissions.**
   "Dwell time on the spatial canvas" / "window-switch rate" map onto this launcher's own window
   focus events (already instrumented for cross-surface continuity) -- no `UsageStatsManager` /
   accessibility-service permission needed.

### On-device (`alfr3d_deck`)
- `contextawareness/AttentionTelemetryStore.kt` (new, DataStore-backed, mirrors
  `AppUsageStore`'s pattern): `recordWindowFocus(layoutKey)` called from
  `WindowManager.focus()`/`.openWindow()` (accumulates per-category dwell ms + switch count),
  `recordUnlock()` called from a new `MainActivity.onResume()` override, `snapshotAndReset()`
  returning a rolling-window snapshot and clearing counters.
- `AttentionTelemetryReporter` (new): own `CoroutineScope`, started from
  `MainActivity.onCreate()`, flushes a snapshot every 15 minutes via a new
  `Alfr3dClient.reportAttentionTelemetry()` (same `requestWithBody` pattern as
  `reportSurfaceState`). Deliberately not piggybacked on `HttpAlfr3dClient`'s 5s connection-probe
  loop -- far too frequent for telemetry.

### Backend (`alfr3d`)
- New route in `services/service_api/routes/context.py`:
  `POST /api/context/attention-telemetry`, upserts `config` under
  `ATTENTION_TELEMETRY_CONFIG_KEY` (`"launcher_attention_telemetry"`), reusing
  `_read_config_json`'s pattern (4th use now).
- `check_attention_focus()`: fires on genuinely high window-switch-rate with dwell *not*
  concentrated in `"media"` -- additive signal alongside (not replacing) the existing
  `check_focus_needed()` calendar heuristic.
- `check_wind_down_signal()`: fires when it's late (`mood_utils.get_day_mood()`'s
  `time_of_day == "night"`) and unlock count is high and dwell is concentrated in `"media"` --
  the milestone's own "inverse case." Suggestion card only, no auto-actuation of lights/Spotify
  (matches every other card built today).
- Both registered in `DISPLAY_RULES`. Thresholds are conservative starting points -- open to
  tuning once real telemetry exists.

## Related
- `services/service_daemon/alfr3ddaemon.py` `check_focus_needed()`, `focus_utils.py` -- untouched
  by this todo, deliberately.
- Notion: "Explore: Nexus Launcher as a new context source for Alfr3d" -- DND-correlation stays
  unbuilt, reconciled above.
