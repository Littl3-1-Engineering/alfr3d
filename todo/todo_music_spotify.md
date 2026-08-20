# Know & Expose Currently-Playing Spotify Music

## Status: ✅ Implemented 2026-08-14

## Overview

ALFR3D should **know what music is currently playing** (which song/artist on Spotify) and be able to **expose it** — via an API endpoint, the event-stream, and situational awareness / voice ("what's playing?").

## What was implemented

- **Event-driven now-playing monitor (Option A + Spotify API)**: `services/service_daemon/utils/now_playing_monitor.py` polls `common.spotify_utils.get_playback_state()` on a background daemon thread (every 10s) and publishes to the `event-stream` Kafka topic **only on transitions**:
  - new song starts → `{"type": "audio", "message": "playing song: <title> by <artist>", "track": {id, name, artists, album, album_art, duration_ms, uri, progress_ms}, "is_playing": true, "time": ...}`
  - playback stops/pauses → `{"type": "audio", "message": "playback stopped", "track": null, "is_playing": false, ...}`
  - Started from `alfr3ddaemon.py` `__main__` (`start_now_playing_monitor()`).
- **Existing endpoint reused**: `GET /api/music/spotify/status` (`services/service_api/routes/music.py`) already returns full playback state; the frontend fetches it once on page load to initialize.
- **No frontend polling**: the Nexus card subscribes to the existing websocket `events` broadcast (delivered by `consume_events()` in `services/service_api/app.py`) and reacts to `type: "audio"` events carrying a `track` key. `EventStream.jsx` shows "playing song: …" with its existing `audio` indicator; `AudioPlayer` ignores the events (no `audio_url`).
- **Nexus card**: `services/service_frontend/src/components/NowPlayingCard.jsx` renders a "N0W PL4Y1NG" tactical panel (album art, title, artist, album, live progress bar, device) in the right column of `Nexus.jsx` above the Guest Roster. Hidden entirely when nothing is playing.
- **Tests**: `TestNowPlayingMonitor` in `tests/test_daemon_service.py` (transition/dedupe/unauthorized cases) and `NowPlayingCard.test.jsx` (Vitest).

## Current State

- **Backend now-playing data:** ✅ `common/spotify_utils.get_playback_state()` + daemon monitor publishes track changes to `event-stream`.
- **Event-stream exposure:** ✅ "playing song: <title> by <artist>" events render in the EventStream and drive the Nexus card.
- **Frontend:** ✅ Now Playing card on the Nexus page (right column), live via websocket, hidden when idle.
- **Situational awareness / voice ("what's playing?"):** Not yet wired — a `music`-mode SA card already renders via `SituationalAwareness.jsx:42`; a future task can push the current track there and add a speak response.

## Files

### Backend (`services/`)
- `services/service_daemon/utils/now_playing_monitor.py` — NEW: monitor loop + pure `evaluate()` transition logic
- `services/service_daemon/alfr3ddaemon.py` — starts the monitor thread
- `services/service_api/routes/music.py` — `GET /api/music/spotify/status` (pre-existing, reused)
- `services/common/spotify_utils.py` — `get_playback_state()` (pre-existing, reused)

### Frontend (`services/service_frontend/src/`)
- `components/NowPlayingCard.jsx` — NEW: Nexus now-playing card
- `pages/Nexus.jsx` — card mounted in the right column above the Guest Roster
- `components/NowPlayingCard.test.jsx` — NEW: Vitest coverage

### Tests
- `tests/test_daemon_service.py` — `TestNowPlayingMonitor`

## Open Questions

- Voice ("what's playing?") via the speak pipeline — future work.
- Launcher-side MediaSession push (Option A in the original plan) can coexist as a fallback source; not required now.
