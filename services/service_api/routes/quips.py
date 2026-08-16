"""Quips management routes."""

import logging
from fastapi import APIRouter, HTTPException, Query
import pymysql

from dependencies import (
    db_connection,
    _get_cached_or_fetch,
    _invalidate_cache,
    _invalidate_cache_pattern,
)
from models import QuipCreate, QuipUpdate

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["quips"])

VALID_CATEGORIES = {"greeting", "weather_joke", "sarcasm", "wisdom", "goodbye", "custom"}


@router.get("/quips")
async def get_quips(category: str | None = Query(default=None)):
    try:
        from dependencies import _fetch_quips

        if category and category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        cache_key = "quips:all" if not category else f"quips:{category}"
        return _get_cached_or_fetch(cache_key, lambda: _fetch_quips(category))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quips: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quips", status_code=201)
async def create_quip(data: QuipCreate):
    try:
        category = data.category or "custom"
        if category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO quips (type, category, quips) VALUES (%s, %s, %s)",
                (data.type, category, data.quips),
            )
            db.commit()
            new_id = cursor.lastrowid
        _invalidate_cache("quips:all")
        _invalidate_cache(f"quips:{category}")
        return {"id": new_id, "type": data.type, "category": category, "quips": data.quips}
    except HTTPException:
        raise
    except pymysql.Error as e:
        logger.error(f"Error creating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/quips/{quip_id}")
async def update_quip(quip_id: int, data: QuipUpdate):
    try:
        category = data.category or "custom"
        if category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE quips SET type = %s, category = %s, quips = %s WHERE id = %s",
                (data.type, category, data.quips, quip_id),
            )
            db.commit()
        _invalidate_cache("quips:all")
        _invalidate_cache(f"quips:{category}")
        return {"id": quip_id, "type": data.type, "category": category, "quips": data.quips}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quips/{quip_id}")
async def delete_quip(quip_id: int):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM quips WHERE id = %s", (quip_id,))
            db.commit()
        _invalidate_cache("quips:all")
        _invalidate_cache_pattern("quips:*")
        return {"message": "Quip deleted"}
    except Exception as e:
        logger.error(f"Error deleting quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
