# Dedupe "now playing" / "playing song" events

## Problem
One audio playback produces multiple lines in the Deck's tactical EVT LOG (and anywhere else
`/api/events` is consumed): a "playing song: <title> by <artist>" audio event *and* a
"Now playing: ..." line. Two sources describe the same fact:

- `services/service_daemon/utils/now_playing_monitor.py` publishes `{"type": "audio", "message": "playing song: ..."}`
- `services/service_sa/sa/engine.py` (`check_now_playing`, ~L1714) emits a "Now playing: ..." SA card/content

## Goal
One event per playback (per track change), not two.

## Tasks
- Trace which of the two paths reaches the `/api/events` stream and which only reaches SA cards
- Pick a single owner for the event (likely the monitor, since SA cards are not a log) and drop or gate the other
- Make sure the SA card still works for the UI if it is kept; only the duplicate *event* goes away
- Keep track-change dedupe (don't re-announce the same track every cycle)
- Verify on the Deck EVT LOG: one line per song

## Notes
Found from alfr3d_deck tactical home style, 2026-10-22. Deck needs no change.
