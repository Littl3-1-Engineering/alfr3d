# Resolve ALFR3D's Music Pick into a Specific, Playable Spotify Playlist

## Status: ✅ Implemented 2026-08-13; backend live-verified 2026-08-25 against a real household Spotify session (see `todo_music_spotify.md`'s "Outstanding" section for the full chain check). On-device: confirmed there is no launcher surface showing this backend data at all -- see `todo_music_spotify.md`'s update for why (Media window is local-device-only by design, Ambient Brief only shows the recommendation card). User decided 2026-08-25 to leave as-is rather than scope new UI.

## Overview

**Historical context (pre-implementation state, resolved by this plan):** before this work, ALFR3D's music
recommendation was text only. `service_daemon/utils/spotify_utils.py:recommend()` maps occupancy/weather/time-of-day
into a mood/genre/energy tuple and a free-text `playlist_hint` (e.g. `"chill, acoustic, lo-fi"`); `check_gatherings()`
in `alfr3ddaemon.py` formatted that into a `mode: "music"` situational-awareness card whose `content` was just a
sentence: `"Play chill, acoustic, lo-fi (acoustic / ambient / lofi, energy=0.2)"`. The old `get_playlist_suggestion()`
was a literal passthrough placeholder with a `TODO: Implement Spotify API integration` comment; it has since been
removed entirely and replaced by the real resolution pipeline described below. There was no playlist id/uri anywhere
in that old pipeline — the alfr3d_deck launcher's "ALFR3D's music pick" card could only regex the mood/genre back out
of that sentence, and its "Play it" button just opened the Spotify app or ran a generic text search (see the
companion plan in `alfr3d_deck/todo/todo_music_playlist_recommendation.md`).

This plan resolves that text hint into one **specific, real Spotify playlist** — id, name, `spotify:playlist:...`
URI, `open.spotify.com` URL, and cover image — so the launcher can deep-link straight into it. It also adds a
general-purpose endpoint so a specific pick is available even when no gathering is in progress (the old card only
fired when a guest was detected home).

**Scoping decisions (confirmed with user):**
- Add an always-available `GET /api/music/recommend/playlist` endpoint, not just resolve the existing
  gathering-triggered card. "Play it" should have something specific behind it most of the time, not only during
  gatherings.
- When resolving a hint into a playlist: **search the household's own saved/owned Spotify playlists first**
  (keyword match against name), and only fall back to a global Spotify playlist search if nothing in the library
  matches.

## Why This Is Mostly Wiring, Not New Infrastructure

Per `todo_music.md` Phase 1 (already `[DONE]`), the real Spotify Web API OAuth client already exists and is
authorized against the household's own Spotify account:
- `services/common/spotify_utils.py` — token storage/refresh, `search(query, types, limit)` (already generic on
  `types`, just never called with `"playlist"`), `get_playlists(limit)` (returns the account's own playlists with
  `id`/`name`/`uri`/`image`/`track_count`), and the existing `play_recommended(hint)` precedent — the exact
  "text hint → search → take top result" pattern this plan mirrors, just for playlists instead of tracks.
- No new OAuth flow, credential storage, or dependency is needed. This is genuinely just: search the library,
  search Spotify, shape the result, thread it through two call sites.

## Tasks

### 1. `services/common/spotify_utils.py` — playlist resolution

- [x] New `find_playlist_for_hint(hint: str, genre: str = "") -> tuple[dict | None, str | None]`:
  - Fetch the household's own playlists via `get_playlists(limit=50)`.
  - Score each by simple case-insensitive word-overlap between `hint`/`genre` and the playlist's `name` (a
    small helper, e.g. `_score_playlist_match(name, keywords)` — tunable heuristic, not a hard science; fine to
    start simple).
  - If the best score clears a minimal threshold, return that playlist shaped as
    `{id, name, uri, url, image, track_count, source: "library"}` (add `url` — `https://open.spotify.com/playlist/{id}`
    — alongside the existing fields `get_playlists` already returns; `external_urls.spotify` is what Spotify's API
    calls it).
  - Otherwise fall back to `search(hint, "playlist", 1)`, take `playlists.items[0]`, shape it the same way with
    `source: "global"`.
  - Returns `(None, "Spotify not connected")` when `is_authorized()` is false, and `(None, err)` on any API
    failure — same tuple convention as the rest of this module. Never raises.

### 2. `services/service_daemon/utils/spotify_utils.py`

- [x] Replaced the placeholder `get_playlist_suggestion()` (and its stale module-docstring TODO at line 5) with
  `resolve_playlist(playlist_hint, genre)`, calling into `common.spotify_utils.find_playlist_for_hint`. Also moved
  `recommend()`/`_normalize_time_of_day()` into `common/spotify_utils.py` (re-exported here for backward
  compatibility) so the new API endpoint (§3) and the daemon share one recommendation engine instead of two
  drifting copies — not in the original plan, but necessary once §3 needed the same mood/genre/energy logic from
  a different process/container.
- [x] `check_gatherings()` in `alfr3ddaemon.py`: after computing `reco`, call the resolver and attach the result
  to the card dict as new fields — `playlist_id`, `playlist_name`, `playlist_uri`, `playlist_url`,
  `playlist_image`, `playlist_source` — **alongside**, not replacing, the existing `content` string. Keep
  `content` byte-for-byte as today: the frontend's `SituationalAwareness.jsx` and the deck's regex-based
  `MusicEnergy.parseAlfr3dSignal` both already depend on that exact format as their fallback path.
  Wrap the resolver call in try/except — if Spotify isn't authorized or the lookup fails, publish the card exactly
  as it does today (`content` only, no playlist fields). The gathering card must never fail to publish because
  Spotify happens to be disconnected.

### 3. New endpoint: `GET /api/music/recommend/playlist`

- [x] Add to `services/service_api/routes/music.py`. Computes current situational inputs itself (no gathering
  required):
  - Occupancy/guest count: same `user`/`states`/`user_types` join `check_gatherings()` already runs — factor this
    query (and the `environment` weather/time lookup) into one small shared helper reused by both the daemon and
    this route, rather than duplicating the SQL a second time. Both processes already query these tables directly
    elsewhere in this codebase, so a shared helper in `common/` (e.g. `common/situational_inputs.py`) matching
    that existing pattern is the natural home.
  - Calls `service_daemon.utils.spotify_utils.recommend(...)` for mood/genre/energy/hint, then
    `find_playlist_for_hint(...)`.
- [x] Response shape: `{ "mood", "genre", "energy", "tempo_hint", "playlist": {...} | null, "error"?: str }`.
  Returns HTTP 200 with `"playlist": null` (not a 4xx) when Spotify isn't connected or nothing was found, so the
  caller can gracefully degrade — this endpoint should never be the reason a client-side fallback path breaks.
- [x] No caching/scheduling needed initially — intended to be called on-demand (e.g. once per Ambient Brief poll
  cycle from the launcher), matching how the rest of the Status Surface data is fetched.

### 4. Frontend — small parity update (optional, cheap since the data's already on the wire)

- [x] `services/service_frontend/src/components/SituationalAwareness.jsx`: when a `mode: "music"` card carries
  `playlist_name`/`playlist_image`/`playlist_url`, show the playlist art + name and link the card to
  `playlist_url` instead of only rendering the plain sentence. Not required for the launcher-side ask, but the
  household display shouldn't lag behind once the data exists.

## Files

- `services/common/spotify_utils.py` — `find_playlist_for_hint`, `_score_playlist_match`, `_playlist_url`,
  `url` field on `get_playlists`, and `recommend`/`_normalize_time_of_day` (moved here from service_daemon)
- `services/service_daemon/utils/spotify_utils.py` — `get_playlist_suggestion` → `resolve_playlist`;
  `recommend`/`_normalize_time_of_day` now re-exported from `common.spotify_utils`
- `services/service_daemon/alfr3ddaemon.py` — `check_gatherings` (attach playlist fields to the card)
- `services/service_api/routes/music.py` — new `GET /api/music/recommend/playlist` + `_current_situational_inputs()`
- `services/service_frontend/src/components/SituationalAwareness.jsx`
- `tests/test_daemon_service.py` — replaced the stale `get_playlist_suggestion` test with one for
  `resolve_playlist`'s graceful-degradation path

**Deviation from the original plan:** did not add a separate `common/situational_inputs.py` shared module. The
daemon (raw `pymysql.connect` per call, its own `MYSQL_*`/`ENV_NAME` env vars) and service_api (the pooled
`common.db_connection()`, `dependencies.ALFR3D_ENV_NAME`) already use two different connection idioms for
genuinely separate reasons — forcing one shared function across both would have fought each service's own
established pattern rather than followed it. `_current_situational_inputs()` lives directly in
`routes/music.py`, written in service_api's own idiom, with the daemon's `check_gatherings()` left as its
existing, independent query. Both compute the same shape of inputs; if they ever need to be reconciled instead
of just resembling each other, revisit this then.

## Explicitly Out of Scope

- **Remote playback via the Spotify Web API** (`POST /me/player/play` with a device id) — requires Spotify
  Premium and an active Spotify Connect device, and doesn't match what was asked for ("play it opens the
  recommended playlist"). This plan is a **deep link** the launcher opens client-side, which sidesteps that
  requirement entirely. The existing playback-control endpoints (`/api/music/spotify/play` etc., from
  `todo_music.md` Phase 1) are unrelated infrastructure this doesn't need to touch.
- **Per-user Spotify accounts** — reuses the single household ALFR3D-authorized account, same as every other
  Spotify feature in this codebase.
- **The "know what's currently playing" effort** tracked separately in `todo_music_spotify.md` — no overlap,
  different data flow (that one is now-playing telemetry; this one is a forward recommendation).

## Open Questions

- Word-overlap matching against library playlist names is a simple heuristic — if it picks bad matches in
  practice (e.g. a playlist literally named "Chill" matching too eagerly), may need a higher threshold or
  Spotify's own playlist `description` field folded into the match, not just `name`.
- Should `check_gatherings()`'s resolved playlist and the new endpoint's resolved playlist be allowed to disagree
  within the same few minutes (e.g. gathering fires mid-poll-cycle while the launcher already cached the general
  pick)? Low-stakes either way since both are "best guess for right now," but worth a glance once both are live.
