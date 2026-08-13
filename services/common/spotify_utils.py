"""Spotify Web API utilities for ALFR3D.

Provides OAuth (Authorization Code flow with token refresh) and playback
control (play/pause/next/previous/seek/volume/queue) via the Spotify Web API.
Credentials are stored in the ``config`` table (spotify_client_id,
spotify_client_secret, spotify_redirect_uri); OAuth tokens are persisted in
``integrations_tokens`` with integration_type='spotify'.
"""

import base64
import logging
import os
from datetime import datetime, timedelta

import requests
import pymysql

from .db_pool import get_connection

logger = logging.getLogger("SpotifyLog")

SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
SPOTIFY_API = "https://api.spotify.com/v1"

SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "streaming "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-read-recently-played "
    "user-library-read"
)

REQUEST_TIMEOUT = 10


def get_spotify_config():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT name, value FROM config WHERE name IN "
            "('spotify_client_id', 'spotify_client_secret', 'spotify_redirect_uri')"
        )
        config = {row[0]: row[1] for row in cursor.fetchall()}
        db.close()
    except pymysql.Error as e:
        logger.error(f"Database error fetching Spotify config: {e}")
        config = {}
    # Fall back to environment variables
    config.setdefault("spotify_client_id", os.environ.get("SPOTIFY_CLIENT_ID", ""))
    config.setdefault("spotify_client_secret", os.environ.get("SPOTIFY_CLIENT_SECRET", ""))
    config.setdefault("spotify_redirect_uri", os.environ.get("SPOTIFY_REDIRECT_URI", ""))
    return config


def is_spotify_configured():
    config = get_spotify_config()
    return bool(config.get("spotify_client_id") and config.get("spotify_client_secret"))


def save_spotify_credentials(client_id, client_secret, redirect_uri=""):
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE config SET value = %s WHERE name = 'spotify_client_id'", (client_id,))
    if cursor.rowcount == 0:
        cursor.execute(
            "INSERT INTO config (name, value) VALUES ('spotify_client_id', %s)",
            (client_id,),
        )
    cursor.execute(
        "UPDATE config SET value = %s WHERE name = 'spotify_client_secret'", (client_secret,)
    )
    if cursor.rowcount == 0:
        cursor.execute(
            "INSERT INTO config (name, value) VALUES ('spotify_client_secret', %s)",
            (client_secret,),
        )
    if redirect_uri:
        cursor.execute(
            "UPDATE config SET value = %s WHERE name = 'spotify_redirect_uri'", (redirect_uri,)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO config (name, value) VALUES ('spotify_redirect_uri', %s)",
                (redirect_uri,),
            )
    db.commit()
    db.close()
    return True


def get_auth_url(state=""):
    """Build the Spotify Authorization Code authorize URL."""
    config = get_spotify_config()
    if not is_spotify_configured():
        return None
    params = {
        "client_id": config["spotify_client_id"],
        "response_type": "code",
        "redirect_uri": config.get("spotify_redirect_uri", ""),
        "scope": SCOPES,
        "show_dialog": "true",
    }
    if state:
        params["state"] = state
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return f"{SPOTIFY_ACCOUNTS}/authorize?{query}"


def _get_tokens():
    """Return stored tokens dict or None."""
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT access_token, refresh_token, expires_at FROM integrations_tokens "
            "WHERE integration_type = 'spotify'"
        )
        row = cursor.fetchone()
        db.close()
    except pymysql.Error as e:
        logger.error(f"Error fetching Spotify tokens: {e}")
        return None
    if not row:
        return None
    return {"access_token": row[0], "refresh_token": row[1], "expires_at": row[2]}


def _store_tokens(access_token, refresh_token, expires_in):
    expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO integrations_tokens "
        "(integration_type, access_token, refresh_token, expires_at) "
        "VALUES ('spotify', %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE access_token = %s, refresh_token = %s, expires_at = %s",
        (access_token, refresh_token, expires_at, access_token, refresh_token, expires_at),
    )
    db.commit()
    db.close()


def _token_expired(tokens):
    if not tokens or not tokens.get("expires_at"):
        return True
    expires_at = tokens["expires_at"]
    if isinstance(expires_at, datetime):
        return datetime.utcnow() >= expires_at - timedelta(seconds=30)
    try:
        expires_dt = datetime.strptime(str(expires_at)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return datetime.utcnow() >= expires_dt - timedelta(seconds=30)


def refresh_access_token():
    """Refresh the Spotify access token using the stored refresh token."""
    config = get_spotify_config()
    tokens = _get_tokens()
    if not tokens or not tokens.get("refresh_token"):
        return None
    auth_header = base64.b64encode(
        f"{config.get('spotify_client_id', '')}:{config.get('spotify_client_secret', '')}".encode()
    ).decode()
    try:
        response = requests.post(
            f"{SPOTIFY_ACCOUNTS}/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
            },
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        _store_tokens(access_token, tokens["refresh_token"], expires_in)
        logger.info("Spotify access token refreshed")
        return access_token
    except Exception as e:
        logger.error(f"Error refreshing Spotify token: {e}")
        return None


def _get_access_token():
    tokens = _get_tokens()
    if not tokens:
        return None
    if _token_expired(tokens):
        return refresh_access_token()
    return tokens.get("access_token")


def is_authorized():
    return bool(_get_access_token())


def _api_request(method, path, params=None, body=None):
    """Make an authenticated request to the Spotify Web API."""
    token = _get_access_token()
    if not token:
        return None, {"error": {"message": "Not authorized", "status": 401}}
    url = f"{SPOTIFY_API}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.request(
            method, url, params=params, json=body, headers=headers, timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 401:
            token = refresh_access_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                response = requests.request(
                    method, url, params=params, json=body, headers=headers, timeout=REQUEST_TIMEOUT
                )
        if response.status_code == 204:
            return {}, None
        if response.status_code >= 400:
            logger.error(f"Spotify API error {response.status_code}: {response.text[:300]}")
            return None, {"error": {"message": response.text[:300], "status": response.status_code}}
        return response.json(), None
    except Exception as e:
        logger.error(f"Spotify API request error: {e}")
        return None, {"error": {"message": str(e), "status": 500}}


def exchange_code(code):
    """Exchange an authorization code for tokens."""
    config = get_spotify_config()
    auth_header = base64.b64encode(
        f"{config.get('spotify_client_id', '')}:{config.get('spotify_client_secret', '')}".encode()
    ).decode()
    try:
        response = requests.post(
            f"{SPOTIFY_ACCOUNTS}/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.get("spotify_redirect_uri", ""),
            },
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        _store_tokens(
            data.get("access_token", ""),
            data.get("refresh_token", ""),
            data.get("expires_in", 3600),
        )
        return True, None
    except Exception as e:
        logger.error(f"Error exchanging Spotify code: {e}")
        return False, str(e)


def get_playback_state():
    data, err = _api_request("GET", "/me/player")
    if err:
        return {"authorized": is_authorized(), "error": err.get("error", {}).get("message")}
    if data is None:
        return {"is_playing": False, "device": None, "item": None, "progress_ms": 0}
    item = data.get("item") or {}
    return {
        "is_playing": data.get("is_playing", False),
        "device": data.get("device"),
        "item": {
            "id": item.get("id"),
            "name": item.get("name"),
            "artists": [a.get("name") for a in (item.get("artists") or [])],
            "album": (item.get("album") or {}).get("name"),
            "album_art": (
                ((item.get("album") or {}).get("images") or [{}])[0].get("url")
                if (item.get("album") or {}).get("images")
                else None
            ),
            "duration_ms": item.get("duration_ms"),
            "uri": item.get("uri"),
        },
        "progress_ms": data.get("progress_ms", 0),
        "shuffle_state": data.get("shuffle_state", False),
        "repeat_state": data.get("repeat_state", "off"),
    }


def get_audio_analysis(track_id):
    """Fetch a trimmed version of Spotify's audio-analysis for a track.

    The full /audio-analysis payload is several hundred KB; we extract only
    the segment timing/loudness data the frontend visualizer needs, encoded as
    compact tuples [start, duration, loudness_start, loudness_max].
    """
    data, err = _api_request("GET", f"/audio-analysis/{track_id}")
    if err:
        return None, err
    if not data:
        return None, {"error": {"message": "No analysis data", "status": 404}}
    track = data.get("track") or {}
    segments = [
        (
            s.get("start", 0),
            s.get("duration", 0),
            s.get("loudness_start", -60.0),
            s.get("loudness_max", -60.0),
        )
        for s in (data.get("segments") or [])
    ]
    return {
        "track_id": track_id,
        "duration": track.get("duration"),
        "tempo": track.get("tempo"),
        "time_signature": track.get("time_signature"),
        "segments": segments,
    }, None


def play(device_id=None, context_uri=None):
    body = {}
    if context_uri:
        body["context_uri"] = context_uri
    params = {"device_id": device_id} if device_id else None
    _, err = _api_request("PUT", "/me/player/play", params=params, body=body or None)
    if err and err.get("error", {}).get("status") == 404:
        return False, "No active device found"
    return err is None, (err.get("error", {}).get("message") if err else None)


def pause():
    _, err = _api_request("PUT", "/me/player/pause")
    return err is None, (err.get("error", {}).get("message") if err else None)


def next_track():
    _, err = _api_request("POST", "/me/player/next")
    return err is None, (err.get("error", {}).get("message") if err else None)


def previous_track():
    _, err = _api_request("POST", "/me/player/previous")
    return err is None, (err.get("error", {}).get("message") if err else None)


def seek(position_ms, device_id=None):
    params = {"position_ms": int(position_ms)}
    if device_id:
        params["device_id"] = device_id
    _, err = _api_request("PUT", "/me/player/seek", params=params)
    return err is None, (err.get("error", {}).get("message") if err else None)


def set_volume(percent, device_id=None):
    params = {"volume_percent": max(0, min(100, int(percent)))}
    if device_id:
        params["device_id"] = device_id
    _, err = _api_request("PUT", "/me/player/volume", params=params)
    return err is None, (err.get("error", {}).get("message") if err else None)


def get_queue():
    data, err = _api_request("GET", "/me/player/queue")
    if err:
        return None, err.get("error", {}).get("message")

    def _simplify(track):
        if not track:
            return None
        return {
            "id": track.get("id"),
            "name": track.get("name"),
            "artists": [a.get("name") for a in (track.get("artists") or [])],
            "album": (track.get("album") or {}).get("name"),
            "duration_ms": track.get("duration_ms"),
            "uri": track.get("uri"),
        }

    return {
        "currently_playing": _simplify(data.get("currently_playing")),
        "queue": [_simplify(t) for t in (data.get("queue") or []) if t],
    }, None


def add_to_queue(uri):
    _, err = _api_request("POST", "/me/player/queue", params={"uri": uri})
    return err is None, (err.get("error", {}).get("message") if err else None)


def get_devices():
    data, err = _api_request("GET", "/me/player/devices")
    if err:
        return [], err.get("error", {}).get("message")
    devices = data.get("devices") or []
    return [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "type": d.get("type"),
            "is_active": d.get("is_active", False),
            "is_restricted": d.get("is_restricted", False),
            "volume_percent": d.get("volume_percent"),
        }
        for d in devices
    ], None


def transfer_playback(device_id):
    _, err = _api_request("PUT", "/me/player", body={"device_ids": [device_id], "play": True})
    return err is None, (err.get("error", {}).get("message") if err else None)


def search(query, types="track", limit=20):
    data, err = _api_request("GET", "/search", params={"q": query, "type": types, "limit": limit})
    if err:
        return {}, err.get("error", {}).get("message")
    return data, None


def _playlist_url(p):
    return (p.get("external_urls") or {}).get("spotify") or (
        f"https://open.spotify.com/playlist/{p.get('id')}" if p.get("id") else None
    )


def get_playlists(limit=20):
    data, err = _api_request("GET", "/me/playlists", params={"limit": limit})
    if err:
        return [], err.get("error", {}).get("message")
    playlists = data.get("items") or []
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "uri": p.get("uri"),
            "url": _playlist_url(p),
            "track_count": p.get("tracks", {}).get("total", 0),
            "image": (p.get("images") or [{}])[0].get("url") if p.get("images") else None,
        }
        for p in playlists
    ], None


def _score_playlist_match(name, keywords):
    """Word-overlap score between a playlist name and hint/genre keywords
    (case-insensitive, substring-tolerant). Deliberately simple/tunable, not
    a hard science."""
    if not name or not keywords:
        return 0
    name_lower = name.lower()
    score = 0
    for kw in keywords:
        kw = kw.strip().lower()
        if len(kw) < 3:
            continue
        if kw in name_lower:
            score += 1
    return score


def find_playlist_for_hint(hint, genre=""):
    """Resolve a text hint (e.g. "chill, acoustic, lo-fi") into one specific,
    real Spotify playlist — the household's own saved playlists are checked
    first (by keyword match against playlist name), falling back to a global
    Spotify playlist search (mirrors the existing play_recommended() "search,
    take the top result" pattern, just for playlists instead of tracks).

    Returns (playlist_dict, None) or (None, error_message). Never raises —
    callers (situational-awareness cards, the recommend/playlist endpoint)
    must be able to degrade gracefully when Spotify isn't connected.
    """
    if not hint:
        return None, "No playlist hint provided"
    if not is_authorized():
        return None, "Spotify not connected"

    try:
        combined = hint.replace("/", " ") + " " + (genre or "").replace("/", " ")
        keywords = combined.replace(",", " ").split()

        library, lib_err = get_playlists(limit=50)
        if not lib_err and library:
            scored = [(p, _score_playlist_match(p.get("name"), keywords)) for p in library]
            scored = [(p, s) for p, s in scored if s > 0]
            if scored:
                scored.sort(key=lambda ps: ps[1], reverse=True)
                best = dict(scored[0][0])
                best["source"] = "library"
                return best, None

        data, err = search(hint, "playlist", 1)
        if err:
            return None, f"Search failed: {err}"
        items = (data.get("playlists") or {}).get("items") or []
        items = [p for p in items if p]
        if not items:
            return None, f"No playlist results for '{hint}'"
        p = items[0]
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "uri": p.get("uri"),
            "url": _playlist_url(p),
            "track_count": (p.get("tracks") or {}).get("total", 0),
            "image": (p.get("images") or [{}])[0].get("url") if p.get("images") else None,
            "source": "global",
        }, None
    except Exception as e:
        logger.error(f"find_playlist_for_hint error: {e}")
        return None, str(e)


def play_recommended(hint):
    """Play a track matching a text hint (searches Spotify, plays top result)."""
    if not hint:
        return False, "No playlist hint provided"
    data, err = search(hint, "track", 1)
    if err:
        return False, f"Search failed: {err}"
    tracks = (data.get("tracks") or {}).get("items") or []
    if not tracks:
        return False, f"No results for '{hint}'"
    uri = tracks[0].get("uri")
    ok, play_err = play(context_uri=uri)
    if not ok:
        return False, play_err or "Play failed"
    return True, None


def search_by_seeds(track_ids, artist_names, limit=20):
    """Find related tracks via Spotify recommendations seeded by track/artist IDs.

    Uses the /recommendations endpoint when seed tracks are available; otherwise
    falls back to a search for the top artist. Returns a list of track dicts.
    """
    try:
        seed_tracks = ",".join(track_ids[:5])
        seed_artists = ""
        if artist_names:
            # Resolve artist names to IDs (limit to 2 seeds)
            data, err = search(artist_names[0], "artist", 1)
            if not err and data:
                artists = (data.get("artists") or {}).get("items") or []
                if artists:
                    seed_artists = artists[0].get("id", "")
        params = {"limit": limit}
        if seed_tracks:
            params["seed_tracks"] = seed_tracks
        if seed_artists:
            params["seed_artists"] = seed_artists
        if not seed_tracks and not seed_artists:
            return [], None
        data, err = _api_request("GET", "/recommendations", params=params)
        if err:
            return [], err.get("error", {}).get("message")
        return data.get("tracks") or [], None
    except Exception as e:
        logger.error(f"search_by_seeds error: {e}")
        return [], str(e)


def _normalize_time_of_day(hour):
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def recommend(total_people, guest_count, time_of_day, weather=None):
    """
    Deterministic mood/genre/energy recommendation from situational inputs.
    Lives in `common` (rather than only `service_daemon`) so both the daemon
    (gathering-triggered situational-awareness card) and the API service
    (on-demand `GET /api/music/recommend/playlist`) share one recommendation
    engine instead of drifting apart. `service_daemon.utils.spotify_utils`
    re-exports this for its existing call sites.

    Args:
        total_people: total number of people present (residents + guests)
        guest_count: number of guests (may be 0)
        time_of_day: one of 'morning','day','evening','night' (or an hour int)
        weather: either a string (e.g. 'rainy', 'sunny') or a dict containing
                 keys like 'subjective_feel', 'description', 'main', 'temp'.

    Returns:
        dict with keys: 'mood','genre','energy'(0-1),'tempo_hint','playlist_hint'
    """
    if time_of_day is None:
        time_of_day = "day"
    if isinstance(time_of_day, int):
        time_of_day = _normalize_time_of_day(time_of_day)

    subj = None
    if isinstance(weather, dict):
        subj = weather.get("subjective_feel") or weather.get("description")
    elif isinstance(weather, str):
        subj = weather

    if total_people <= 1:
        energy = 0.2
    elif total_people <= 3:
        energy = 0.4
    elif total_people <= 6:
        energy = 0.7
    else:
        energy = 0.9

    if guest_count and guest_count > 0:
        energy += 0.08

    if time_of_day in ("evening", "night"):
        energy += 0.05
    if time_of_day == "morning":
        energy -= 0.05

    if subj:
        low_energy_keywords = ["rain", "drizzle", "snow", "cold", "bad weather"]
        high_energy_keywords = ["sunny", "perfect", "pleasant", "warm"]
        s = subj.lower()
        if any(k in s for k in low_energy_keywords):
            energy -= 0.12
        if any(k in s for k in high_energy_keywords):
            energy += 0.06

    energy = max(0.0, min(1.0, energy))

    if energy < 0.3:
        genre = "acoustic / ambient / lofi"
        mood = "relaxed"
        tempo = "slow"
        playlist_hint = (
            "chill, acoustic, lo-fi" if subj and "rain" in str(subj).lower() else "acoustic, mellow"
        )
    elif energy < 0.6:
        genre = "indie / soft pop / jazz"
        mood = "warm"
        tempo = "medium"
        playlist_hint = "indie / soft pop / mellow jazz"
    elif energy < 0.8:
        genre = "alt-rock / upbeat pop / nu-disco"
        mood = "upbeat"
        tempo = "medium-fast"
        playlist_hint = "upbeat pop, alt-rock, nu-disco"
    else:
        genre = "dance / house / party hits"
        mood = "energetic"
        tempo = "fast"
        playlist_hint = "party, dance, high-energy"

    descriptor = f"{mood} {genre.split('/')[0].strip()}"

    return {
        "mood": descriptor,
        "genre": genre,
        "energy": round(energy, 2),
        "tempo_hint": tempo,
        "playlist_hint": playlist_hint,
    }
