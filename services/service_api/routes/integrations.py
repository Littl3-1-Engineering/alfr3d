"""Integration sync routes (Calendar, Gmail)."""

import logging
from fastapi import APIRouter, HTTPException
import pymysql
from kafka.errors import KafkaError

from dependencies import db_connection, get_producer

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["integrations"])


@router.put("/integrations/openweather/config")
async def save_openweather_config(data: dict):
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("UPDATE config SET value = %s WHERE name = 'openWeather'", (api_key,))
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES ('openWeather', %s)",
                    (api_key,),
                )
            db.commit()
        _invalidate_environment_cache()
        return {"message": "OpenWeatherMap configuration saved"}
    except pymysql.Error as e:
        logger.error(f"Error saving openweather config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _invalidate_environment_cache():
    try:
        from dependencies import _invalidate_cache
        _invalidate_cache("api:weather")
        _invalidate_cache("api:environment")
    except Exception:
        pass


@router.post("/integrations/calendar/sync")
async def trigger_calendar_sync():
    try:
        message = {"type": "calendar", "action": "sync"}
        producer = get_producer()
        producer.send("integrations", message)
        producer.flush()
        logger.info("Calendar sync triggered")
        return {"message": "Calendar sync triggered"}
    except KafkaError as e:
        logger.error(f"Kafka error triggering calendar sync: {e}")
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")
    except Exception as e:
        logger.error(f"Error triggering calendar sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/integrations/gmail/sync")
async def trigger_gmail_sync():
    try:
        message = {"type": "gmail", "action": "sync"}
        producer = get_producer()
        producer.send("integrations", message)
        producer.flush()
        logger.info("Gmail sync triggered")
        return {"message": "Gmail sync triggered"}
    except KafkaError as e:
        logger.error(f"Kafka error triggering gmail sync: {e}")
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")
    except Exception as e:
        logger.error(f"Error triggering gmail sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrations/status")
async def get_integrations_status():
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT integration_type FROM integrations_tokens WHERE integration_type = 'google'"
            )
            rows = cursor.fetchall()
            cursor.execute("SELECT value FROM config WHERE name = 'openWeather'")
            owm_row = cursor.fetchone()
        connected = bool(rows)
        owm_connected = bool(owm_row and owm_row[0])

        spotify_status = {
            "configured": False,
            "authorized": False,
        }
        try:
            from common import spotify_utils
            spotify_status = {
                "configured": spotify_utils.is_spotify_configured(),
                "authorized": spotify_utils.is_authorized(),
            }
        except Exception as e:
            logger.error(f"Error checking Spotify status: {str(e)}")

        return {
            "google": connected,
            "openweather": owm_connected,
            "spotify": spotify_status,
        }
    except pymysql.Error as e:
        logger.error(f"Error checking integrations status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
