"""Quips management routes."""

import logging
from fastapi import APIRouter, HTTPException
import pymysql

from dependencies import get_connection, _get_cached_or_fetch, _invalidate_cache
from models import QuipCreate, QuipUpdate

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["quips"])


@router.get("/quips")
async def get_quips():
    try:
        from dependencies import _fetch_quips
        return _get_cached_or_fetch("quips:all", lambda: _fetch_quips())
    except Exception as e:
        logger.error(f"Error fetching quips: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quips", status_code=201)
async def create_quip(data: QuipCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("INSERT INTO quips (type, quips) VALUES (%s, %s)", (data.type, data.quips))
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        _invalidate_cache("quips:all")
        return {"id": new_id, "type": data.type, "quips": data.quips}
    except pymysql.Error as e:
        logger.error(f"Error creating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/quips/{quip_id}")
async def update_quip(quip_id: int, data: QuipUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE quips SET type = %s, quips = %s WHERE id = %s",
            (data.type, data.quips, quip_id),
        )
        db.commit()
        db.close()
        _invalidate_cache("quips:all")
        return {"id": quip_id, "type": data.type, "quips": data.quips}
    except Exception as e:
        logger.error(f"Error updating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quips/{quip_id}")
async def delete_quip(quip_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM quips WHERE id = %s", (quip_id,))
        db.commit()
        db.close()
        _invalidate_cache("quips:all")
        return {"message": "Quip deleted"}
    except Exception as e:
        logger.error(f"Error deleting quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
