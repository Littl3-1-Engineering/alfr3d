# Know & Expose Currently-Playing Spotify Music

## Status: Option B implemented 2026-08-17 — unit-tested, not yet verified against a live Spotify-authorized deployment

## Overview

ALFR3D should **know what music is currently playing** (which song/artist on Spotify) and be able to **expose it** — via an API endpoint, the event-stream, and situational awareness / voice ("what's playing?").

## Decision: Option B first (backend-only), Option A deferred

Investigation (2026-08-17) found **most of Option B already exists**, which tips the scope decisively: `services/service_api/routes/music.py` already exposes `GET /api/music/spotify/status`, backed by `spotify_utils.get_playback_state()` (`services/common/spotify_utils.py`), which calls Spotify's `GET /me/player` (a superset of `/me/player/currently-playing`) through the existing OAuth client and already returns `is_playing`, `item.{name,artists,album,album_art,duration_ms,uri}`, `progress_ms`, `device`. There's no new Spotify integration to build — the remaining gap is narrower: **poll it, detect changes, persist the last-known value, and publish an event on change.**

Option A (launcher push, any app) stays a documented fast-follow — pick it up only if the household ever needs coverage for non-Spotify apps or a Spotify account the backend isn't authorized for. Not scoped further here; see the original section below.

## Implementation Plan (Option B)

### Phase 1: Poller + persistence — ✅ DONE
- Implemented as a new `DISPLAY_RULES` entry (`("now_playing", 3.1, "check_now_playing")`) in `alfr3ddaemon.py` rather than a separate `schedule` job — the daemon's outer loop only ticks every 60s (`MyDaemon.run()`), the same floor a `schedule.every(20).seconds` job would hit anyway, and `DISPLAY_RULES` already runs every cycle at that cadence.
- `check_now_playing()` calls `spotify_api.get_playback_state()` (via a local `from common import spotify_utils as spotify_api`, mirroring `check_party_advisory()`) — no new Spotify API call needed.
- Persists to `config` (`music_now_playing` key) via `_read_now_playing_config()` / `_write_now_playing_config()`, following the UPDATE-then-INSERT-if-0-rows pattern. Stores `{track_id, title, artist, is_playing, updated_at}` — no album art, and title/artist are capped at 150 chars each as a defensive margin under the `VARCHAR(512)` column.
- Only writes + publishes when `track_id` or `is_playing` actually changed vs. the last-persisted value.

### Phase 2: Event-stream on change — ✅ DONE
- Publishes via `get_producer()` on change, `type: "audio"` with a pre-formatted `message: "Now playing: {title} by {artist}"` — zero `EventStream.jsx` changes needed, as planned.

### Phase 3: Situational-awareness card — ✅ DONE
- `check_now_playing()` returns `{"mode": "music", "content": ..., "priority": 3.1, "track_title": ..., "track_artist": ..., "is_playing": ...}`.
- `SituationalAwareness.jsx` extended with a small block rendering `card.track_title`/`card.track_artist` (distinct from the existing `playlist_name` block, which is still driven by `check_gatherings()`'s recommendation card — the two coexist as separate `mode: "music"` cards at priorities 3 and 3.1).

### Phase 4: Read endpoint — ✅ DONE
- Added `GET /api/music/now-playing` (`services/service_api/routes/music.py`) — fast local read of the persisted `config` value, no live Spotify call. `GET /api/music/spotify/status` (pre-existing) is unchanged and still does the live proxy.

### Outstanding
- **Live verification against a real Spotify-authorized deployment** — not yet done. Unit tests (`tests/test_daemon_service.py::TestCheckNowPlaying`, `tests/test_api_service.py`) cover the logic with mocked DB/Spotify calls, but nothing has exercised this against a live household Spotify session yet. Fold into the alfr3d_deck on-device verification pass (same "not yet verified live" gap as the playlist-recommendation plan).
- Confirm the `schedule`-vs-60s-loop assumption doesn't need revisiting if "now playing" ever needs sub-60s freshness (not currently required).

## Files (Option B) — implemented

- `services/service_daemon/alfr3ddaemon.py` — `check_now_playing()`, `_read_now_playing_config()`/`_write_now_playing_config()`, `NOW_PLAYING_CONFIG_KEY`, `DISPLAY_RULES` entry
- `services/common/spotify_utils.py` — unchanged, `get_playback_state()` reused as-is
- `services/service_api/routes/music.py` — `GET /api/music/now-playing`
- `services/service_frontend/src/components/SituationalAwareness.jsx` — track title/artist block for `music`-mode cards
- `tests/test_daemon_service.py` (`TestCheckNowPlaying`, `TestDecideDisplays` updates), `tests/test_api_service.py` (`test_api_get_now_playing_*`)

## Option A: Launcher → Backend push (deferred fast-follow, not scoped)

The launcher already captures now-playing on-device for **any** music app (Spotify, YT Music, etc.) via `alfr3d_deck`'s `media/NowPlayingController.kt` (`MediaSessionManager.getActiveSessions()` → `NowPlayingSnapshot(appLabel, title, artist, isPlaying)`) and `media/MediaNotificationListener.kt` (notification-access grant gates cross-app session enumeration; deliberately doesn't read notification content). Currently only shown in the launcher's own Media window (`media/ui/MediaWindowContent.kt`) — never pushed to the backend.

If picked up later:
- New launcher API call, e.g. `POST /api/music/now-playing` (add to `alfr3d_deck`'s `Alfr3dClient.kt` + `HttpAlfr3dClient.kt`, push `NowPlayingSnapshot` on change via `LaunchedEffect`/`StateFlow` collection).
- Backend accepts the push into the same Phase 1 persistence/event-stream path above (`source: "launcher"` vs `source: "spotify"` to distinguish).
- Works for any device-streaming app, no Spotify OAuth needed; complements rather than replaces Option B (Option B still covers "what's playing" when nothing's active on the launcher device, or a different app/account is in use elsewhere).

## Open Questions — resolved during implementation

- ~~Confirm `schedule` library sub-minute job granularity~~ — moot; folded into the existing 60s `DISPLAY_RULES` cycle instead of a separate `schedule` job.
- ~~`config.value VARCHAR(512)` fit~~ — resolved by dropping album art from the persisted value and capping title/artist at 150 chars each.
- ~~Whether Phase 4's fast-read endpoint is worth adding~~ — added; cheap and matches the original "voice / API" ask.
