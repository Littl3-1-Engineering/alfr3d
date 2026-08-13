"""Audio casting utilities for ALFR3D.

Discovers speaker targets from Home Assistant ``media_player`` entities, manages
``speaker_groups`` (whole-home zones), casts the current Spotify playback to a
speaker or group, and controls per-speaker volume.

Spotify "Connect" is the preferred transport: we hand off playback to a
Spotify-compatible device when one is present; otherwise we fall back to Home
Assistant ``media_player.play_media`` so the HA entity plays the same context.
"""

import logging
import orjson
import pymysql

from .db_pool import get_connection
from . import ha_utils
from . import spotify_utils

logger = logging.getLogger("AudioCastLog")


def get_speakers():
    """List available speakers (HA media_player entities) with cast status."""
    speakers = []
    states = ha_utils.get_ha_states()
    for state in states:
        entity_id = state.get("entity_id", "")
        if not entity_id.startswith("media_player."):
            continue
        attrs = state.get("attributes", {})
        speakers.append(
            {
                "entity_id": entity_id,
                "name": attrs.get("friendly_name", entity_id),
                "state": state.get("state"),
                "volume_level": attrs.get("volume_level"),
                "is_volume_muted": attrs.get("is_volume_muted", False),
                "source": attrs.get("source"),
                "media_title": attrs.get("media_title"),
                "media_artist": attrs.get("media_artist"),
                "media_content_id": attrs.get("media_content_id"),
            }
        )
    return speakers


def _get_groups():
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, name, entities FROM speaker_groups ORDER BY name")
        rows = cursor.fetchall()
        db.close()
        for row in rows:
            entities = row["entities"]
            row["entities"] = (
                orjson.loads(entities) if isinstance(entities, str) else (entities or [])
            )
        return rows
    except pymysql.Error as e:
        logger.error(f"Error fetching speaker groups: {e}")
        return []


def get_groups():
    """List speaker groups with their entities."""
    return _get_groups()


def create_group(name, entities):
    """Create (or replace) a speaker group by name."""
    if not name or not entities:
        return False, "name and entities are required"
    db = get_connection()
    cursor = db.cursor()
    payload = orjson.dumps([e for e in entities if e]).decode("utf-8")
    try:
        cursor.execute(
            "INSERT INTO speaker_groups (name, entities) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE entities = VALUES(entities)",
            (name, payload),
        )
        db.commit()
        db.close()
        return True, None
    except pymysql.Error as e:
        logger.error(f"Error creating speaker group: {e}")
        db.rollback()
        db.close()
        return False, str(e)


def delete_group(group_id):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM speaker_groups WHERE id = %s", (group_id,))
        db.commit()
        db.close()
        return True, None
    except pymysql.Error as e:
        logger.error(f"Error deleting speaker group: {e}")
        return False, str(e)


def _cast_spotify(context_uri, volume=None):
    """Try Spotify Connect first (set volume, transfer/play). Returns (ok, err)."""
    ok, err = spotify_utils.play(context_uri=context_uri)
    if not ok:
        return False, err or "Spotify play failed"
    if volume is not None:
        spotify_utils.set_volume(volume)
    return True, None


def _ha_play(entity_id, context_uri, media_title=""):
    """Cast via Home Assistant media_player.play_media."""
    data = {
        "media_content_id": context_uri or media_title,
        "media_content_type": "music",
    }
    ok, err = ha_utils.ha_control_device(entity_id, "play_media", data)
    if ok:
        ha_utils.ha_control_device(entity_id, "turn_on", None)
    return ok, err


def cast_to_speaker(entity_id, context_uri=None, volume=None):
    """Cast current playback to a single speaker."""
    if not entity_id:
        return False, "entity_id is required"

    ok, err = _cast_spotify(context_uri, volume)
    if ok:
        logger.info(f"Cast to '{entity_id}' via Spotify Connect")
        return True, None

    logger.info(f"Spotify Connect unavailable, using HA play_media for '{entity_id}'")
    ok, err = _ha_play(entity_id, context_uri or "", "")
    if ok:
        return True, None
    return False, err or "Cast failed"


def cast_to_group(group_name, context_uri=None, volume=None):
    """Cast to a speaker group (each entity plays the same context)."""
    groups = _get_groups()
    group = next((g for g in groups if g["name"].lower() == group_name.lower()), None)
    if not group:
        return False, f"Group '{group_name}' not found"
    entities = group.get("entities") or []
    if not entities:
        return False, "Group has no entities"

    ok, err = _cast_spotify(context_uri, volume)
    if ok:
        logger.info(f"Cast to group '{group_name}' via Spotify Connect")
        return True, None

    results = []
    for entity in entities:
        ok, err = _ha_play(entity, context_uri or "", "")
        results.append((entity, ok))
    if any(ok for _e, ok in results):
        return True, None
    return False, "Failed to cast to any speaker in group"


def stop_cast():
    """Stop casting (pause Spotify, stop media on HA speakers)."""
    spotify_utils.pause()
    for speaker in get_speakers():
        if speaker.get("state") == "playing":
            ha_utils.ha_control_device(speaker["entity_id"], "media_stop", None)
            ha_utils.ha_control_device(speaker["entity_id"], "turn_off", None)
    return True, None


def set_speaker_volume(entity_id, volume):
    """Set volume on a single HA speaker (0-100)."""
    volume = max(0, min(100, int(volume)))
    ok, err = ha_utils.ha_control_device(entity_id, "volume_set", {"volume_level": volume / 100.0})
    return ok, err


def set_group_volume(group_name, volume):
    """Set volume across every entity in a group."""
    groups = _get_groups()
    group = next((g for g in groups if g["name"].lower() == group_name.lower()), None)
    if not group:
        return False, f"Group '{group_name}' not found"
    volume = max(0, min(100, int(volume)))
    results = []
    for entity in group.get("entities") or []:
        ok, err = ha_utils.ha_control_device(entity, "volume_set", {"volume_level": volume / 100.0})
        results.append((entity, ok))
    if any(ok for _e, ok in results):
        return True, None
    return False, "Failed to set volume on any speaker in group"


def get_cast_status():
    """Return speaker/group cast status: which speakers are playing."""
    speakers = get_speakers()
    groups = _get_groups()
    playing = [
        s["entity_id"]
        for s in speakers
        if s.get("state") in ("playing", "paused") and s.get("media_content_id")
    ]
    return {
        "speakers": speakers,
        "groups": groups,
        "active_casts": playing,
    }
