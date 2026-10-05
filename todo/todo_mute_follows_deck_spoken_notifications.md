# check_mute should honor the Deck's "speak notifications on device" setting

## Status: built 2026-10-05, tests green, NOT yet deployed or verified live (uncommitted in both repos)

**Spec (Athos, 2026-10-05) -- four scenarios:**
1. Nobody home, no Deck with PHONE SPEECH on -> backend generates **no audio**.
2. Nobody home, a Deck with PHONE SPEECH on -> speaks on the Deck.
3. Someone home, Deck user away (relay on) -> speaks at both.
4. Someone home, Deck user home -> backend only (the Deck relay self-suppresses while its owner is online).

**Built.** Keyed off the Deck's `tts_relay_enabled` toggle (a "reachable only" signal was tried and dropped:
it can't tell scenario 1 from 2). The opt-in is the user's; a fresh snapshot (<15 min) proves reachability.
- Deck: `DeviceSnapshotReport.speechRelayEnabled` -> `speech.relay_enabled`, sent by `DeviceContextReporter`
  every 5 min (a toggle change takes up to ~5 min to reach the backend).
- Backend: facet whitelisted in `routes/context.py`; `db_utils.deck_relay_available()` (fresh + `relay_enabled is True`,
  fails closed); `check_mute_optimized` = `is_sleeping or (is_empty_house and not deck_relay_available())`;
  **`service_speak` now discards an empty-house speak request when no relay is available** (it previously
  always emitted for the Deck relay, which broke scenario 1 for every ungated speak caller).
  Quiet hours stay authoritative. The 5 `check_mute` wrappers already delegate to one function.
- Known limit: in scenario 2 the `audio` event also carries `audio_url`, so any house player listening to the
  event stream could still play it into the empty house; the Deck can't be addressed exclusively.
- Tests: `TestCheckMuteDeckRelay`, two `service_speak` scenario tests, `test_device_snapshot_keeps_speech_relay_facet`;
  backend 437 pass; Deck ktlint/detekt/unit/assembleDebug pass (ktlint baseline regenerated -- line-keyed).
- **Still owed:** deploy to NUC + install Deck, then verify live (owner away -> gated line produces an `audio` event and the phone speaks it; owner home -> Deck silent).

Ask: `check_mute` (backend) should follow the Alfr3d Deck setting that speaks notifications on
the device (`spoken_notifications_enabled`, `Alfr3dSettingsStore.kt`). When that setting is
**enabled**, ALFR3D should still **generate speech even if there are no worthy listeners at
home**, and **push the notifications to the Deck** so the device speaks/shows them.

## Where to look

- `check_mute` copies: `services/service_user/app.py:70`, `services/service_environment/environment.py:57`,
  `services/service_environment/weather_util.py:51`, `services/service_daemon/alfr3ddaemon.py:610`,
  `services/service_daemon/utils/util_routines.py`; all funnel into `db_utils.check_mute_optimized`.
  Callers gate speak sends with `if not check_mute():`.
- Deck-side prior art: `alfr3d_deck/todo/todo_spoken_notifications.md` (Deck -> backend direction,
  `POST /api/context/notification-event`). This todo is the reverse direction: backend -> Deck.
- Consumer-reported UI state lives under `service_api/routes/context.py` — likely the way the
  Deck's toggle reaches the backend.

## Open questions

- Does the Deck setting need to be reported to the backend (new context field), or is there one already?
- Mute semantics: does "enabled" bypass only the *no listeners home* gate, or also DayContext
  quiet hours / explicit user mute? Recommendation: bypass presence only; explicit mute and quiet hours stay authoritative.
- Delivery: reuse the existing Deck push path (WebSocket/event stream) or add a speak-to-device event type?
- Consolidate the 5 duplicated `check_mute` copies while here, rather than patching each.
