"""Routine management routes."""

import logging
from fastapi import APIRouter, HTTPException
import orjson
import pymysql

from dependencies import get_connection, get_producer, _get_cached_or_fetch, _invalidate_cache, normalize_time, ALFR3D_ENV_NAME
from models import RoutineCreate, RoutineUpdate

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
async def create_routine(data: RoutineCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            db.close()
            raise HTTPException(status_code=400, detail="Environment not found")
        env_id = env_row[0]

        actions_json = orjson.dumps(data.actions).decode("utf-8")
        recurrence = data.recurrence
        routine_time = normalize_time(data.time)

        cursor.execute(
            "INSERT INTO routines (name, time, enabled, recurrence, actions, environment_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (data.name, routine_time, data.enabled, recurrence, actions_json, env_id),
        )
        db.commit()
        routine_id = cursor.lastrowid
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Created routine: {data.name} (ID: {routine_id})")
        return {"id": routine_id, "message": "Routine created"}
    except Exception as e:
        logger.error(f"Error creating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/routines/{routine_id}")
async def update_routine(routine_id: int, data: RoutineUpdate):
    try:
        db = get_connection()
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

        if not updates:
            db.close()
            raise HTTPException(status_code=400, detail="No valid fields to update")

        values.append(routine_id)
        query = f"UPDATE routines SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, values)
        db.commit()
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Updated routine ID: {routine_id}")
        return {"message": "Routine updated"}
    except Exception as e:
        logger.error(f"Error updating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/routines/{routine_id}")
async def delete_routine(routine_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM routines WHERE id = %s", (routine_id,))
        db.commit()
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Deleted routine ID: {routine_id}")
        return {"message": "Routine deleted"}
    except Exception as e:
        logger.error(f"Error deleting routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routines/{routine_id}/run")
async def run_routine(routine_id: int):
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT r.*, e.name as env_name FROM routines r "
            "JOIN environment e ON r.environment_id = e.id WHERE r.id = %s",
            (routine_id,),
        )
        routine = cursor.fetchone()

        if not routine:
            db.close()
            raise HTTPException(status_code=404, detail="Routine not found")

        actions = orjson.loads(routine["actions"]) if routine.get("actions") else []

        cursor.execute("UPDATE routines SET last_run = NOW() WHERE id = %s", (routine_id,))
        db.commit()
        db.close()

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

        return {"message": "Routine executed", "actions_run": len(actions)}
    except Exception as e:
        logger.error(f"Error running routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
