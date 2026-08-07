# Plan to Implement Music System (Spotify Integration + Recommender)

## Phase 1: Spotify Playback Integration

### Goal
Enable actual Spotify playback through alfr3d — play, pause, skip, volume, and queue management via the Spotify API.

### Tasks
- Register Spotify app and obtain OAuth credentials (Client ID, Client Secret) — *user action: developer.spotify.com*
- [DONE] Implement OAuth flow for user authorization (token storage + refresh) — `services/common/spotify_utils.py` (Authorization Code + refresh via `integrations_tokens` table, `integration_type='spotify'`)
- [DONE] Create `services/common/spotify_utils.py` with:
  - Authentication and token refresh
  - Playback control (play, pause, next, previous, seek)
  - Volume control
  - Queue management (add to queue, get queue)
  - Playlist fetching and playback
  - Search functionality
- [DONE] Add API endpoints (in `services/service_api/routes/music.py`, registered in `app.py`):
  - GET/POST `/api/music/spotify/auth` — OAuth flow (+ GET/POST `/api/music/spotify/callback` for code exchange)
  - GET `/api/music/spotify/status` — current playback state
  - POST `/api/music/spotify/play` — play (with optional context URI)
  - POST `/api/music/spotify/pause`
  - POST `/api/music/spotify/next` / `previous`
  - POST `/api/music/spotify/volume` — set volume
  - GET `/api/music/spotify/queue`
  - POST `/api/music/spotify/queue/add` — add track to queue
  - GET `/api/music/spotify/devices` — list available playback devices
  - POST `/api/music/spotify/device` — transfer playback to device
  - GET `/api/music/spotify/search` + GET `/api/music/spotify/playlists`
- [DONE] Create frontend component `Music.jsx` (lazy-loaded tab in `Matrix.jsx`):
  - Now-playing display (track, artist, album art, progress bar)
  - Play/pause, next/previous, seek, volume slider
  - Queue view
  - Playlist browser
  - Search tracks
  - Device selector / transfer
  - Credential setup + OAuth authorize flow (with callback URL helper)
- [DONE] **Audio visualizer** — bar visualizer driven by Spotify audio-analysis segment loudness, synced to playback position via rAF; idle animation fallback. `AudioVisualizer.jsx` + `GET /api/music/spotify/audio-analysis/{track_id}` (trimmed server-side)
- [DONE] Add Spotify control to voice command system:
  - `music`/`spotify` action type in `execute_actions` (`util_routines.py`) + `run_routine` (`routes/routines.py`) via `_execute_music_action` (play, pause, next, previous, volume, search+play)
  - Routines UI: "Music (Spotify)" action type with action dropdown + search query / volume inputs
  - Daemon `play_tune()` now plays a context-aware track via `spotify_utils.play_recommended`; scheduled at 08:00

---

## Phase 2: Better Recommender Engine

### Goal
Replace basic shuffle with an intelligent music recommender that learns from listening history, context, and user preferences.

### Tasks
- [DONE] Create listening history table (migration):
  - `listening_history` — `setup/migration_013_listening_history.sql` + alembic revision `0013_listening_history.py` (track_id, album, artist, played_at, context, source)
- [DONE] Implement `services/common/recommender_engine.py` with:
  - **Collaborative filtering**: top-artist + recent-pattern seeding via Spotify `/recommendations`
  - **Context-aware recommendations**: time of day (morning/day/evening/night) + weekday/weekend
  - **Genre/artist clustering**: top-artist seeding and artist-ID seeds
  - **Rediscovery**: tracks not played in 14 days surfaced with a "Rediscovered" reason
  - Every recommendation carries an explainable `reason` label
  - `record_listening()` persists plays from the frontend into `listening_history`
- [DONE] Expose API:
  - GET `/api/music/recommend` — get recommended tracks (with reason labels)
  - GET `/api/music/recommend/refresh` — regenerate recommendation pool
  - POST `/api/music/history` — record a played track
- [DONE] Frontend integration (`Music.jsx`):
  - "Recommended for You" section in Music.jsx
  - "Play Recommendations" button + per-track play/add-to-queue
  - Reason label (e.g., "Because you listen to X" / "Morning vibes" / "Rediscovered")
  - Auto-records the now-playing track into listening history when it changes
- [DONE] Daemon background task: `rebuild_music_recommendations()` scheduled every 6h

---

## Phase 3: Cast to Smarthome Speakers ✓

### Goal
Cast audio playback to smarthome speakers (Home Assistant media_player entities, Sonos, Chromecast Audio) for whole-home audio.

### Tasks
- [DONE] Discover and list available speaker targets via Home Assistant media_player entities
- [DONE] Add `speaker_groups` table for defining speaker zones/groups (e.g., "Living Room", "Whole House") — `setup/migration_014_speaker_groups.sql`
- [DONE] Implement `services/common/audio_cast.py` with:
  - Cast to single speaker via HA media_player.play_media
  - Cast to speaker group (sync playback across multiple speakers)
  - Volume control per speaker and per group
  - Fallback: if Spotify Connect device is available, use that instead
- [DONE] Extend API (`services/service_api/routes/music.py`):
  - GET `/api/music/speakers` — list available speakers and groups + active cast status
  - POST `/api/music/cast` — cast current playback to speaker(s)
  - POST `/api/music/cast/stop` — stop casting
  - POST `/api/music/cast/volume` — per-target volume
  - POST `/api/music/speakers/groups` — create/delete speaker groups
- [DONE] Frontend additions to Music.jsx:
  - Speaker picker with room/zone labels
  - "Cast to..." button next to device selector
  - Per-speaker volume sliders
  - Active cast indicator
- [DONE] Voice commands: `cast` / `stop_cast` actions in `util_routines.py` (execute_actions) — "cast to living room", "play in whole house"

---

## Phase 4: Multi-Source Audio (Future)

### Goal
Support multiple audio sources beyond Spotify (local library, Tidal, YouTube Music, radio).

### Tasks
- Abstract `AudioSource` interface
- Add source registry with priority/fallback
- Unified queue across sources
- Source-specific controls in frontend

---

## Future Ideas
- Mood-based playlists (chill, focus, party, workout)
- Integration with routines (e.g., "play morning playlist at 7 AM")
- Voice-controlled playback with NLU ("play something like Radiohead")
- Scrobbling to Last.fm
- Multi-room sync
