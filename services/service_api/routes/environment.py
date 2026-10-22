"""Environment, weather, and calendar routes."""

import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
import pymysql

from dependencies import (
    db_connection,
    _get_cached_or_fetch,
    _invalidate_cache,
    manager,
    ALFR3D_ENV_NAME,
)
from models import EnvironmentUpdate, MuteHoursUpdate
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["environment"])


@router.get("/weather")
async def get_weather():
    try:
        from dependencies import _fetch_weather

        weather_data = _get_cached_or_fetch("api:weather", _fetch_weather, ttl=300)
        if weather_data:
            await manager.broadcast("weather", weather_data)
            return weather_data
        raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching weather: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environment")
async def get_environment():
    try:
        from dependencies import _fetch_environment

        env_data = _get_cached_or_fetch("api:environment", _fetch_environment, ttl=300)
        if env_data:
            await manager.broadcast("environment", env_data)
            return env_data
        raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/environment")
async def update_environment(
    data: EnvironmentUpdate, _perm=Depends(require_permission("environment", "update"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            updates = []
            params = []
            field_mappings = {
                "latitude": "latitude",
                "longitude": "longitude",
                "city": "city",
                "state": "state",
                "country": "country",
                "ip": "IP",
                "temp_min": "low",
                "temp_max": "high",
                "description": "description",
                "pressure": "pressure",
                "humidity": "humidity",
                "subjective_feel": "subjective_feel",
            }
            location_fields = [
                "latitude",
                "longitude",
                "city",
                "state",
                "country",
                "ip",
            ]
            manual_location_override = (
                1 if any(getattr(data, f) is not None for f in location_fields) else 0
            )
            for field, db_field in field_mappings.items():
                value = getattr(data, field, None)
                if value is not None:
                    updates.append(f"{db_field} = %s")
                    params.append(value)
            updates.append("manual_location_override = %s")
            params.append(manual_location_override)
            if updates:
                params.append(ALFR3D_ENV_NAME)
                sql = f"UPDATE environment SET {', '.join(updates)} WHERE name = %s"
                cursor.execute(sql, params)
                db.commit()
        _invalidate_cache("api:weather")
        _invalidate_cache("api:environment")
        return {
            "message": "Environment updated",
            "manual_location_override": manual_location_override,
        }
    except pymysql.Error as e:
        logger.error(f"Error updating environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


MUTE_START_KEY = "mute_start"
MUTE_END_KEY = "mute_end"
DEFAULT_MUTE_START = "22:00"
DEFAULT_MUTE_END = "07:00"


@router.get("/environment/mute-hours")
async def get_mute_hours():
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT name, value FROM config WHERE name IN (%s, %s)",
                (MUTE_START_KEY, MUTE_END_KEY),
            )
            stored = dict(cursor.fetchall())
        return {
            "start": stored.get(MUTE_START_KEY) or DEFAULT_MUTE_START,
            "end": stored.get(MUTE_END_KEY) or DEFAULT_MUTE_END,
        }
    except pymysql.Error as e:
        logger.error(f"Error fetching mute hours: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/environment/mute-hours")
async def update_mute_hours(
    data: MuteHoursUpdate,
    _perm=Depends(require_permission("environment", "update_mute_hours")),
):
    if data.start == data.end:
        raise HTTPException(status_code=422, detail="start and end must differ")
    try:
        with db_connection() as db:
            cursor = db.cursor()
            for key, value in ((MUTE_START_KEY, data.start), (MUTE_END_KEY, data.end)):
                cursor.execute("UPDATE config SET value = %s WHERE name = %s", (value, key))
                if cursor.rowcount == 0:
                    cursor.execute("INSERT INTO config (name, value) VALUES (%s, %s)", (key, value))
            db.commit()
        return {"message": "Mute hours updated", "start": data.start, "end": data.end}
    except pymysql.Error as e:
        logger.error(f"Error updating mute hours: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/events")
async def get_calendar_events():
    try:
        with db_connection() as db:
            cursor = db.cursor()
            today = datetime.now().date()
            cursor.execute(
                "SELECT title, start_time, end_time, address, notes FROM calendar_events "
                "WHERE start_time >= %s AND start_time < %s + INTERVAL 1 DAY "
                "ORDER BY start_time ASC",
                (today, today),
            )
            events = [
                {
                    "title": row[0],
                    "start_time": row[1].isoformat() + "Z" if row[1] else None,
                    "end_time": row[2].isoformat() + "Z" if row[2] else None,
                    "address": row[3],
                    "notes": row[4],
                }
                for row in cursor.fetchall()
            ]
            cursor.execute("SELECT timezone FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            tz_row = cursor.fetchone()
            timezone = tz_row[0] if tz_row else None
            return {"events": events, "timezone": timezone}
    except pymysql.Error as e:
        logger.error(f"Error fetching calendar events: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/environment/reset")
async def reset_environment(_perm=Depends(require_permission("environment", "reset"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
                "description, sunrise, sunset, pressure, humidity, manual_override, "
                "manual_location_override, subjective_feel FROM environment WHERE name = %s",
                (ALFR3D_ENV_NAME,),
            )
            _ = cursor.fetchone()
        _invalidate_cache("api:weather")
        _invalidate_cache("api:environment")
        return {"message": "Environment reset to auto-detect"}
    except pymysql.Error as e:
        logger.error(f"Error resetting environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_calendar_events_data():
    """Fetch calendar events from DB, returns {events, timezone} dict."""
    with db_connection() as db:
        cursor = db.cursor()
        today = datetime.now().date()
        cursor.execute(
            "SELECT title, start_time, end_time, address, notes FROM calendar_events "
            "WHERE start_time >= %s AND start_time < %s + INTERVAL 1 DAY ORDER BY start_time ASC",
            (today, today),
        )
        events = [
            {
                "title": row[0],
                "start_time": row[1].isoformat() + "Z" if row[1] else None,
                "end_time": row[2].isoformat() + "Z" if row[2] else None,
                "address": row[3],
                "notes": row[4],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute("SELECT timezone FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        tz_row = cursor.fetchone()
        timezone = tz_row[0] if tz_row else None
        return {"events": events, "timezone": timezone}


async def broadcast_calendar_events():
    """Background task: broadcast calendar events every 5 minutes."""
    while True:
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, _fetch_calendar_events_data)
            await manager.broadcast("calendar_events", data)
        except Exception as e:
            logger.error(f"Error broadcasting calendar events: {str(e)}")
        await asyncio.sleep(300)
