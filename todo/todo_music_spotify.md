# Know & Expose Currently-Playing Spotify Music

## Status: 🔲 TODO

## Overview

ALFR3D should **know what music is currently playing** (which song/artist on Spotify) and be able to **expose it** — via an API endpoint, the event-stream, and situational awareness / voice ("what's playing?").

## Current State

- **Backend has full Spotify OAuth, but no now-playing data.** `services/common/spotify_utils.py` (752 lines) now provides a real OAuth (authorization-code + refresh) client and playback/search/playlist API — `services/service_daemon/utils/spotify_utils.py` is a thin re-export of it (`resolve_playlist`, `recommend`, etc.), no longer a standalone rule-only stub. What's still missing is a "what's currently playing" read: nothing polls `GET /v1/me/player/currently-playing` or exposes a now-playing endpoint. Option B below is therefore largely just "add a poller + endpoint on top of the OAuth client that already exists," not a from-scratch integration.
- **Frontend has a placeholder only.** `Integrations.jsx:15` lists "Spotify — Music playlist suggestions" with `integrationType: null` (nothing wired to a backend). `SituationalAwareness.jsx:42` already renders a `music`-mode icon, so a music card can be surfaced with no frontend change.
- **The launcher already has on-device now-playing.** The Nexus Launcher (`/home/athos/Projects/Alfr3d/alfr3d_launcher`) reads the active system `MediaSession` via:
  - `media/NowPlayingController.kt` — `MediaSessionManager.getActiveSessions()`, produces `NowPlayingSnapshot(appLabel, title, artist, isPlaying)` (incl. play/pause/skip controls).
  - `media/MediaNotificationListener.kt` — a `NotificationListenerService` whose **notification-access grant** is the OS gate for cross-app session enumeration. Currently deliberately does **not** read notification content.
  - This snapshot is only shown in the launcher's Media window (`media/ui/MediaWindowContent.kt`); it is **not pushed to the ALFR3D backend** (`alfr3d/Alfr3dClient.kt` / `HttpAlfr3dClient.kt` only do GETs of environment/weather/users/devices/routines/events/SA/calendar).

## Two Data Sources (choose one or both)

### Option A: Launcher → Backend push (recommended first)
The launcher already captures now-playing on-device for **any** music app (Spotify, YT Music, etc.) and already has a backend HTTP client.

- Push `NowPlayingSnapshot` from `NowPlayingController` to ALFR3D on snapshot changes (poll/`StateFlow` collection in a `LaunchedEffect`).
- New launcher API call, e.g. `POST /api/music/now-playing` (add to `Alfr3dClient.kt` + `HttpAlfr3dClient.kt`).
- No Spotify OAuth needed; works for any device-streaming app; survives whatever the user actually plays.

### Option B: Spotify Web API (backend-side)
- Real OAuth client (authorization-code flow, refresh token) in a new `service_daemon/utils/spotify_api.py` or `service_speak/...`.
- Poll `GET https://api.spotify.com/v1/me/player/currently-playing` for `{track, artist, album, is_playing, progress_ms, duration_ms}`.
- Store credentials in `config` table (like `llm_api_key`); add integration status to `Integrations.jsx` (replace the `integrationType: null` Spotify placeholder).
- Works even when nothing is playing on the launcher device, but needs user Spotify auth.

## Backend Exposure Plan

1. **Endpoint**: `GET /api/music/now-playing` in `services/service_api/routes/` (new `routes/music.py`), returning `{ source, title, artist, album, app, is_playing, progress_ms, duration_ms, timestamp }`; `404`/`null` when nothing is playing.
2. **Storage**: keep a lightweight "current track" record — e.g. columns in `config` (`music_now_playing` JSON) or a small `now_playing` table — so the value survives restarts and is queryable.
3. **Event-stream**: publish changes to the `event-stream` Kafka topic (e.g. `{"type": "music", "title": ..., "artist": ...}`) so:
   - the frontend `EventStream.jsx` shows "Now playing: X by Y",
   - situational awareness can generate a `music`-mode card (`SituationalAwareness.jsx` already renders that icon),
   - the butler can answer "what's playing?" via the speak pipeline.
4. **Frontend**: add a Now Playing card/panel (Matrix → Integrations, and/or a small live tile) fed by the endpoint + event-stream.
5. **Launcher**: optionally also surface the backend-confirmed track back in the Media window for consistency.

## Files

### Backend (`/home/athos/Projects/Alfr3d/alfr3d`)
- `services/service_daemon/utils/spotify_utils.py` (extend or replace with real API)
- `services/service_api/routes/music.py` (new — `GET/POST /api/music/now-playing`)
- `services/service_api/app.py` / router registration
- `services/service_api/models.py` (`NowPlayingUpdate`)
- `services/service_frontend/src/components/Integrations.jsx`
- `services/service_frontend/src/components/EventStream.jsx` / `SituationalAwareness.jsx`

### Launcher (`/home/athos/Projects/Alfr3d/alfr3d_launcher`)
- `app/src/main/java/com/alfr3d/launcher/media/NowPlayingController.kt`
- `app/src/main/java/com/alfr3d/launcher/alfr3d/Alfr3dClient.kt` / `HttpAlfr3dClient.kt`
- `app/src/main/java/com/alfr3d/launcher/alfr3d/model/Alfr3dModels.kt`
- `app/src/main/java/com/alfr3d/launcher/media/ui/MediaWindowContent.kt`

## Open Questions

- Should the backend trust the launcher push (Option A) or require authenticated Spotify (Option B)? Both can coexist — launcher push as live source, Spotify API as fallback/cross-device.
- Token/credential storage + OAuth UX for Option B (match existing `llm_api_key` config pattern).
- Rate/`state` dedup: only push/emit when title/artist/is_playing actually changes.
