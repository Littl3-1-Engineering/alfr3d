"""Integration sync routes (Calendar, Gmail)."""

import logging
from fastapi import APIRouter, HTTPException
import pymysql
from kafka.errors import KafkaError

from dependencies import get_connection, get_producer

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["integrations"])


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
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT integration_type FROM integrations_tokens WHERE integration_type = 'google'"
        )
        rows = cursor.fetchall()
        db.close()
        connected = bool(rows)
        return {"google": connected}
    except pymysql.Error as e:
        logger.error(f"Error checking integrations status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
