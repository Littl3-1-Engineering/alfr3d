# check_mute should honor the Deck's "speak notifications on device" setting

## Status: built + backend deployed 2026-10-05; NOT yet verified live (Deck build not installed on a device)

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
- **Committed/deployed 2026-10-05:** backend `cec2f7bd` pushed to `main` and deployed to the NUC (rebuilt + recreated
  `service-api/-speak/-daemon/-user/-environment`, all healthy; no migration). Deck `12533fe` committed locally,
  **not pushed or released**. `deck_relay_available()` returns False on the NUC until a Deck reports the new field.
- **Still owed:** install the Deck build, turn PHONE SPEECH on, wait <=5 min for the report, then verify the four
  scenarios live (owner away + relay on -> phone speaks a gated line; relay off + empty house -> no audio generated;
  owner home -> Deck silent).
