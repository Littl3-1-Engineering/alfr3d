"""Routine management routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException
import orjson
import pymysql

from dependencies import (
    db_connection,
    get_producer,
    _get_cached_or_fetch,
    _invalidate_cache,
    normalize_time,
    ALFR3D_ENV_NAME,
)
from models import RoutineCreate, RoutineUpdate
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["routines"])


@router.get("/routines")
async def get_routines():
    try:
        from dependencies import _fetch_routines

        cache_key = f"routines:{ALFR3D_ENV_NAME}"
        return _get_cached_or_fetch(cache_key, lambda: _fetch_routines())
    except Exception as e:
        logger.error(f"Error fetching routines: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routines", status_code=201)
async def create_routine(
    data: RoutineCreate, _perm=Depends(require_permission("routines", "create"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            env_row = cursor.fetchone()
            if not env_row:
                raise HTTPException(status_code=400, detail="Environment not found")
            env_id = env_row[0]

            actions_json = orjson.dumps(data.actions).decode("utf-8")
            triggers_json = orjson.dumps(data.triggers).decode("utf-8")
            conditions_json = orjson.dumps(data.conditions).decode("utf-8")
            recurrence = data.recurrence
            routine_time = normalize_time(data.time)

            cursor.execute(
                "INSERT INTO routines (name, time, enabled, recurrence, actions, triggers, "
                "conditions, environment_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    data.name,
                    routine_time,
                    data.enabled,
                    recurrence,
                    actions_json,
                    triggers_json,
                    conditions_json,
                    env_id,
                ),
            )
            db.commit()
            routine_id = cursor.lastrowid
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Created routine: {data.name} (ID: {routine_id})")
        return {"id": routine_id, "message": "Routine created"}
    except Exception as e:
        logger.error(f"Error creating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/routines/{routine_id}")
async def update_routine(
    routine_id: int, data: RoutineUpdate, _perm=Depends(require_permission("routines", "update"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            updates = []
            values = []
            if data.name is not None:
                updates.append("name = %s")
                values.append(data.name)
            if data.time is not None:
                updates.append("time = %s")
                values.append(normalize_time(data.time))
            if data.enabled is not None:
                updates.append("enabled = %s")
                values.append(data.enabled)
            if data.recurrence is not None:
                updates.append("recurrence = %s")
                values.append(data.recurrence)
            if data.actions is not None:
                updates.append("actions = %s")
                values.append(orjson.dumps(data.actions).decode("utf-8"))
            if data.triggers is not None:
                updates.append("triggers = %s")
                values.append(orjson.dumps(data.triggers).decode("utf-8"))
            if data.conditions is not None:
                updates.append("conditions = %s")
                values.append(orjson.dumps(data.conditions).decode("utf-8"))

            if not updates:
                raise HTTPException(status_code=400, detail="No valid fields to update")

            values.append(routine_id)
            query = f"UPDATE routines SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, values)
            db.commit()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Updated routine ID: {routine_id}")
        return {"message": "Routine updated"}
    except Exception as e:
        logger.error(f"Error updating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/routines/{routine_id}")
async def delete_routine(routine_id: int, _perm=Depends(require_permission("routines", "delete"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM routines WHERE id = %s", (routine_id,))
            db.commit()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Deleted routine ID: {routine_id}")
        return {"message": "Routine deleted"}
    except Exception as e:
        logger.error(f"Error deleting routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routines/{routine_id}/run")
async def run_routine(routine_id: int, _perm=Depends(require_permission("routines", "run"))):
    try:
        with db_connection() as db:
            cursor = db.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                "SELECT r.*, e.name as env_name FROM routines r "
                "JOIN environment e ON r.environment_id = e.id WHERE r.id = %s",
                (routine_id,),
            )
            routine = cursor.fetchone()

            if not routine:
                raise HTTPException(status_code=404, detail="Routine not found")

            actions = orjson.loads(routine["actions"]) if routine.get("actions") else []

            cursor.execute("UPDATE routines SET last_run = NOW() WHERE id = %s", (routine_id,))
            db.commit()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")

        kafka_producer = get_producer()
        if not kafka_producer:
            raise HTTPException(status_code=500, detail="Kafka not available")

        for action in actions:
            action_type = action.get("type")
            action_params = action.get("params", {})

            if action_type == "speak":
                message = {"text": action_params.get("text", ""), "engine": "Coqui"}
                kafka_producer.send("speak", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent speak action")
            elif action_type == "device":
                device_id = action_params.get("device_id")
                device_action = action_params.get("action", "on")
                message = {"device_id": device_id, "action": device_action}
                kafka_producer.send("device", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent device action")
            elif action_type == "email":
                message = {
                    "type": "email",
                    "to": action_params.get("to", ""),
                    "subject": action_params.get("subject", ""),
                    "body": action_params.get("body", ""),
                }
                kafka_producer.send("user", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent email action")
            elif action_type in ("thermostat_set", "lock", "unlock", "cover_open", "cover_close"):
                success, message = _control_iot_device(
                    action_params.get("device_id"),
                    action_type,
                    action_params,
                )
                if success:
                    logger.info(f"Routine {routine_id}: {action_type} action ok")
                else:
                    logger.error(f"Routine {routine_id}: {action_type} action failed: {message}")
            elif action_type in ("music", "spotify"):
                ok, message = _execute_music_action(action_params)
                if ok:
                    logger.info(f"Routine {routine_id}: music action ok: {message}")
                else:
                    logger.error(f"Routine {routine_id}: music action failed: {message}")

        return {"message": "Routine executed", "actions_run": len(actions)}
    except Exception as e:
        logger.error(f"Error running routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _control_iot_device(device_id, action_type, params):
    """Control an IoT device (smarthome_devices) for routine actions."""
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT source, ha_entity_id, device_type FROM smarthome_devices WHERE id = %s",
            (device_id,),
        )
        row = cursor.fetchone()

    if not row:
        return False, "IoT device not found"
    source, ha_entity_id, _ = row

    if source != "homeassistant" or not ha_entity_id:
        return False, "Unsupported source or unlinked entity"

    from common import ha_utils

    if action_type == "thermostat_set":
        temperature = params.get("temperature")
        success, message = ha_utils.ha_control_device(
            ha_entity_id, "set_temperature", {"temperature": temperature}
        )
        if not success:
            return success, message
        mode = params.get("mode")
        if mode:
            success, message = ha_utils.ha_control_device(ha_entity_id, "set_mode", {"mode": mode})
        return success, message
    elif action_type == "lock":
        return ha_utils.ha_control_device(ha_entity_id, "lock", None)
    elif action_type == "unlock":
        return ha_utils.ha_control_device(ha_entity_id, "unlock", None)
    elif action_type == "cover_open":
        return ha_utils.ha_control_device(ha_entity_id, "set_cover_position", {"position": 100})
    elif action_type == "cover_close":
        return ha_utils.ha_control_device(ha_entity_id, "set_cover_position", {"position": 0})
    return False, "Unknown action type"


def _execute_music_action(params):
    """Execute a music/Spotify action (play, pause, next, previous, search+play, cast)."""
    from common import spotify_utils, audio_cast

    action = (params.get("action") or "play").lower()
    query = params.get("query") or params.get("text") or ""
    try:
        if action == "pause":
            return spotify_utils.pause()
        if action == "next":
            return spotify_utils.next_track()
        if action == "previous":
            return spotify_utils.previous_track()
        if action == "volume":
            return spotify_utils.set_volume(params.get("volume_percent", 50))
        if action == "cast":
            entity_id = params.get("entity_id")
            group_name = params.get("group_name")
            volume = params.get("volume_percent")
            if entity_id:
                ok, err = audio_cast.cast_to_speaker(entity_id, volume=volume)
            elif group_name:
                ok, err = audio_cast.cast_to_group(group_name, volume=volume)
            else:
                return False, "entity_id or group_name is required for cast"
            return ok, err or "Cast completed"
        if action == "stop_cast":
            return audio_cast.stop_cast()
        if query:
            data, err = spotify_utils.search(query, "track", 1)
            if err:
                return False, f"Search failed: {err}"
            tracks = (data.get("tracks") or {}).get("items") or []
            if not tracks:
                return False, f"No results for '{query}'"
            uri = tracks[0].get("uri")
            ok, err = spotify_utils.play(context_uri=uri)
            if not ok:
                return False, err or "Play failed"
            return True, f"Playing '{tracks[0].get('name')}'"
        return spotify_utils.play()
    except Exception as e:
        return False, str(e)
