"""Environment, weather, and calendar routes."""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import pymysql

from dependencies import get_connection, manager, ALFR3D_ENV_NAME
from models import EnvironmentUpdate

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["environment"])


@router.get("/weather")
async def get_weather():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel, timezone FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            weather_data = {
                "city": row[4],
                "state": row[5],
                "country": row[6],
                "low": row[8],
                "high": row[9],
                "description": row[10],
                "sunrise": row[11].isoformat() if row[11] else None,
                "sunset": row[12].isoformat() if row[12] else None,
                "pressure": row[13],
                "humidity": row[14],
                "timezone": row[18],
            }
            await manager.broadcast("weather", weather_data)
            return weather_data
        else:
            raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching weather: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environment")
async def get_environment():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel, timezone FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            env_data = {
                "id": row[0],
                "name": row[1],
                "latitude": row[2],
                "longitude": row[3],
                "city": row[4],
                "state": row[5],
                "country": row[6],
                "ip": row[7],
                "temp_min": row[8],
                "temp_max": row[9],
                "description": row[10],
                "sunrise": row[11].isoformat() if row[11] else None,
                "sunset": row[12].isoformat() if row[12] else None,
                "pressure": row[13],
                "humidity": row[14],
                "manual_override": row[15],
                "manual_location_override": row[16],
                "subjective_feel": row[17],
                "timezone": row[18],
            }
            await manager.broadcast("environment", env_data)
            return env_data
        else:
            raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/environment")
async def update_environment(data: EnvironmentUpdate):
    try:
        db = get_connection()
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
        location_fields = ["latitude", "longitude", "city", "state", "country", "ip"]
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
        db.close()
        return {
            "message": "Environment updated",
            "manual_location_override": manual_location_override,
        }
    except pymysql.Error as e:
        logger.error(f"Error updating environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/events")
async def get_calendar_events():
    try:
        db = get_connection()
        cursor = db.cursor()
        today = datetime.now().date()
        cursor.execute(
            "SELECT title, start_time, end_time, address, notes FROM calendar_events "
            "WHERE DATE(start_time) = %s ORDER BY start_time ASC",
            (today,),
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
        db.close()
        return {"events": events, "timezone": timezone}
    except pymysql.Error as e:
        logger.error(f"Error fetching calendar events: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/environment/reset")
async def reset_environment():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        _ = cursor.fetchone()
        db.close()
        return {"message": "Environment reset to auto-detect"}
    except pymysql.Error as e:
        logger.error(f"Error resetting environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
