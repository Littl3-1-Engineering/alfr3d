"""Spotify / music routes."""

import logging

from fastapi import APIRouter, HTTPException, Query

from common import spotify_utils, db_connection, db_utils
from dependencies import ALFR3D_ENV_NAME

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["music"])


def _current_situational_inputs():
    """Occupancy, time-of-day, and weather for right now — the same shape of
    inputs `alfr3ddaemon.py`'s `check_gatherings()` computes for its
    gathering-triggered card, but on-demand and independent of "is a guest
    home", so `/music/recommend/playlist` can resolve a specific playlist at
    any time, not only during a detected gathering."""
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN ut.type IN ('guest') THEN 1 ELSE 0 END) as guest_count,
                COUNT(*) as total_count
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            WHERE s.state = 'online' AND u.username != 'unknown'
            """
        )
        row = cursor.fetchone()
        guest_count = row[0] if row and row[0] else 0
        total_count = row[1] if row and row[1] else 0

        cursor.execute(
            "SELECT description, subjective_feel FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        desc_row = cursor.fetchone()
        desc, subj = desc_row if desc_row else (None, None)

    hour = db_utils.get_env_local_time(ALFR3D_ENV_NAME).hour
    if 6 <= hour < 18:
        time_of_day = "day"
    elif 18 <= hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    return total_count, guest_count, time_of_day, {"description": desc, "subjective_feel": subj}


@router.get("/music/spotify/status")
async def get_status():
    try:
        state = spotify_utils.get_playback_state()
        return state
    except Exception as e:
        logger.error(f"Error getting Spotify status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/auth")
async def get_auth():
    """Return auth state + (if unconfigured) a hint, else the authorize URL."""
    try:
        configured = spotify_utils.is_spotify_configured()
        authorized = spotify_utils.is_authorized() if configured else False
        return {
            "configured": configured,
            "authorized": authorized,
            "auth_url": spotify_utils.get_auth_url() if configured and not authorized else None,
        }
    except Exception as e:
        logger.error(f"Error getting Spotify auth state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/auth")
async def save_credentials(data: dict):
    """Store Spotify client credentials (client_id, client_secret, redirect_uri)."""
    try:
        client_id = (data.get("client_id") or "").strip()
        client_secret = (data.get("client_secret") or "").strip()
        redirect_uri = (data.get("redirect_uri") or "").strip()
        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="client_id and client_secret are required")
        spotify_utils.save_spotify_credentials(client_id, client_secret, redirect_uri)
        return {"message": "Spotify credentials saved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Spotify credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/callback")
async def auth_callback(code: str = Query(default=""), error: str = Query(default="")):
    """OAuth callback — exchanges the authorization code for tokens."""
    try:
        if error:
            raise HTTPException(status_code=400, detail=f"Authorization failed: {error}")
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        ok, err = spotify_utils.exchange_code(code)
        if not ok:
            raise HTTPException(status_code=500, detail=err or "Failed to exchange code")
        return {"message": "Spotify authorized"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Spotify callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/play")
async def play(data: dict = None):
    try:
        data = data or {}
        ok, err = spotify_utils.play(
            device_id=data.get("device_id"), context_uri=data.get("context_uri")
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Play failed")
        return {"message": "Playing"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error playing Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/audio-analysis/{track_id}")
async def get_track_analysis(track_id: str):
    """Trimmed audio-analysis (segments + timing) used by the visualizer."""
    try:
        analysis, err = spotify_utils.get_audio_analysis(track_id)
        if err:
            status = (err.get("error") or {}).get("status", 500)
            detail = (err.get("error") or {}).get("message", "Failed to fetch analysis")
            raise HTTPException(status_code=status, detail=detail)
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching audio analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/pause")
async def pause():
    try:
        ok, err = spotify_utils.pause()
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Pause failed")
        return {"message": "Paused"}
    except Exception as e:
        logger.error(f"Error pausing Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/next")
async def next_track():
    try:
        ok, err = spotify_utils.next_track()
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Next failed")
        return {"message": "Next"}
    except Exception as e:
        logger.error(f"Error skipping Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/previous")
async def previous_track():
    try:
        ok, err = spotify_utils.previous_track()
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Previous failed")
        return {"message": "Previous"}
    except Exception as e:
        logger.error(f"Error skipping back Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/seek")
async def seek(data: dict):
    try:
        position_ms = int(data.get("position_ms", 0))
        ok, err = spotify_utils.seek(position_ms, data.get("device_id"))
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Seek failed")
        return {"message": "Seeked"}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="position_ms must be an integer")
    except Exception as e:
        logger.error(f"Error seeking Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/volume")
async def volume(data: dict):
    try:
        percent = int(data.get("volume_percent", 0))
        ok, err = spotify_utils.set_volume(percent, data.get("device_id"))
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Volume failed")
        return {"message": "Volume set"}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="volume_percent must be an integer")
    except Exception as e:
        logger.error(f"Error setting Spotify volume: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/queue")
async def queue():
    try:
        data, err = spotify_utils.get_queue()
        if err:
            raise HTTPException(status_code=400, detail=err)
        return data
    except Exception as e:
        logger.error(f"Error getting Spotify queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/queue/add")
async def add_to_queue(data: dict):
    try:
        uri = data.get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="uri is required")
        ok, err = spotify_utils.add_to_queue(uri)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Add to queue failed")
        return {"message": "Added to queue"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to Spotify queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/devices")
async def devices():
    try:
        data, err = spotify_utils.get_devices()
        if err:
            raise HTTPException(status_code=400, detail=err)
        return {"devices": data}
    except Exception as e:
        logger.error(f"Error getting Spotify devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/spotify/device")
async def transfer(data: dict):
    try:
        device_id = data.get("device_id")
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        ok, err = spotify_utils.transfer_playback(device_id)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Transfer failed")
        return {"message": "Playback transferred"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transferring Spotify playback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/search")
async def search(q: str = Query(default=""), limit: int = Query(default=20, ge=1, le=50)):
    try:
        if not q.strip():
            return {"tracks": []}
        data, err = spotify_utils.search(q, "track", limit)
        if err:
            raise HTTPException(status_code=400, detail=err)
        tracks = data.get("tracks", {}).get("items") or []
        return {
            "tracks": [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "artists": [a.get("name") for a in (t.get("artists") or [])],
                    "album": (t.get("album") or {}).get("name"),
                    "album_art": (
                        ((t.get("album") or {}).get("images") or [{}])[0].get("url")
                        if (t.get("album") or {}).get("images")
                        else None
                    ),
                    "duration_ms": t.get("duration_ms"),
                    "uri": t.get("uri"),
                }
                for t in tracks
            ]
        }
    except Exception as e:
        logger.error(f"Error searching Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/spotify/playlists")
async def playlists(limit: int = Query(default=20, ge=1, le=50)):
    try:
        data, err = spotify_utils.get_playlists(limit)
        if err:
            raise HTTPException(status_code=400, detail=err)
        return {"playlists": data}
    except Exception as e:
        logger.error(f"Error getting Spotify playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/recommend")
async def recommend(limit: int = Query(default=20, ge=1, le=50)):
    try:
        from common import recommender_engine

        return recommender_engine.recommend(limit=limit)
    except Exception:
        logger.exception("Error generating recommendations")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/music/recommend/playlist")
async def recommend_playlist():
    """On-demand mood/genre/energy recommendation resolved into one specific,
    real Spotify playlist — the household's own saved playlists are checked
    first (keyword match), falling back to a global Spotify playlist search.
    Unlike the gathering-triggered `mode: "music"` situational-awareness card,
    this works any time, so a client always has something specific to play.
    Returns `"playlist": null` (not a 4xx) when Spotify isn't connected or
    nothing matched — callers should degrade gracefully, not treat it as an error.
    """
    try:
        total_people, guest_count, time_of_day, weather = _current_situational_inputs()
        reco = spotify_utils.recommend(
            total_people=total_people,
            guest_count=guest_count,
            time_of_day=time_of_day,
            weather=weather,
        )
        hint = reco.get("playlist_hint") or reco.get("mood") or ""
        playlist, err = spotify_utils.find_playlist_for_hint(hint, reco.get("genre", ""))
        response = {
            "mood": reco.get("mood"),
            "genre": reco.get("genre"),
            "energy": reco.get("energy"),
            "tempo_hint": reco.get("tempo_hint"),
            "playlist": playlist,
        }
        if not playlist and err:
            response["error"] = "Unable to fetch playlist recommendation right now"
        return response
    except Exception:
        logger.exception("Error generating playlist recommendation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/music/recommend/refresh")
async def refresh_recommendations():
    try:
        from common import recommender_engine

        recommender_engine.build_recommendation_pool()
        return {"message": "Recommendation pool refreshed"}
    except Exception:
        logger.exception("Error refreshing recommendations")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/music/history")
async def record_history(data: dict):
    """Record a played track so the recommender can learn preferences."""
    try:
        from common import recommender_engine

        track_id = data.get("track_id") or data.get("id")
        if not track_id:
            raise HTTPException(status_code=400, detail="track_id is required")
        recommender_engine.record_listening(
            track_id=track_id,
            track_name=data.get("name") or data.get("track_name"),
            album=data.get("album"),
            artist=(
                ", ".join(data.get("artists") or []) if data.get("artists") else data.get("artist")
            ),
            context=data.get("context"),
        )
        return {"message": "Recorded"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording listening history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music/speakers")
async def get_speakers():
    """List available speaker targets and groups + active cast status."""
    try:
        from common import audio_cast

        return audio_cast.get_cast_status()
    except Exception as e:
        logger.error(f"Error listing speakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/cast")
async def cast(data: dict):
    """Cast current playback to a speaker or group."""
    try:
        from common import audio_cast

        context_uri = data.get("context_uri")
        volume = data.get("volume_percent")
        entity_id = data.get("entity_id")
        group_name = data.get("group_name")
        if entity_id:
            ok, err = audio_cast.cast_to_speaker(entity_id, context_uri, volume)
        elif group_name:
            ok, err = audio_cast.cast_to_group(group_name, context_uri, volume)
        else:
            raise HTTPException(status_code=400, detail="entity_id or group_name is required")
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Cast failed")
        return {"message": "Cast started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error casting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/cast/stop")
async def stop_cast():
    try:
        from common import audio_cast

        ok, err = audio_cast.stop_cast()
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Stop failed")
        return {"message": "Cast stopped"}
    except Exception as e:
        logger.error(f"Error stopping cast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/speakers/groups")
async def manage_groups(data: dict):
    """Create/replace a speaker group."""
    try:
        from common import audio_cast

        name = (data.get("name") or "").strip()
        entities = data.get("entities") or []
        if data.get("action") == "delete":
            ok, err = audio_cast.delete_group(data.get("id"))
        else:
            ok, err = audio_cast.create_group(name, entities)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Group operation failed")
        return {"message": "Speaker group saved"}
    except Exception as e:
        logger.error(f"Error managing speaker groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/music/cast/volume")
async def cast_volume(data: dict):
    """Set volume on a speaker or a group."""
    try:
        from common import audio_cast

        volume = data.get("volume_percent")
        if volume is None:
            raise HTTPException(status_code=400, detail="volume_percent is required")
        entity_id = data.get("entity_id")
        group_name = data.get("group_name")
        if entity_id:
            ok, err = audio_cast.set_speaker_volume(entity_id, volume)
        elif group_name:
            ok, err = audio_cast.set_group_volume(group_name, volume)
        else:
            raise HTTPException(status_code=400, detail="entity_id or group_name is required")
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Volume failed")
        return {"message": "Volume set"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting cast volume: {e}")
        raise HTTPException(status_code=500, detail=str(e))
