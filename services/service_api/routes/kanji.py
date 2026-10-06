"""Daily kanji wisdom quote.

The backend owns the quote list (``kanji_wisdom`` table, seeded from migration 042); the Deck and
the web frontend show one entry per day. Without an ALFR3D connection the Deck falls back to its
own built-in list, so this endpoint is a refinement, never a dependency.
"""

import logging
from datetime import date

import pymysql
from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_permission
from common import get_day_context
from dependencies import (
    ALFR3D_ENV_NAME,
    _get_cached_or_fetch,
    _invalidate_cache,
    db_connection,
)
from models import KanjiQuoteCreate, KanjiQuoteUpdate

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["kanji"])

_CACHE_KEY = "kanji:enabled"


def pick_for_day(quotes, day):
    """Deterministic one-per-day pick from an id-ordered list of enabled quotes, so every
    surface shows the same quote on the same household-local date. None when the list is empty."""
    if not quotes:
        return None
    return quotes[day.toordinal() % len(quotes)]


def _household_today():
    """Household-local date (env timezone); falls back to the server date if that lookup fails."""
    try:
        return get_day_context(ALFR3D_ENV_NAME).now.date()
    except Exception as e:  # noqa: BLE001 -- never fail the quote over a timezone lookup
        logger.warning(f"kanji: household date lookup failed, using server date: {e}")
        return date.today()


def _row(row):
    return {
        "id": row[0],
        "kanji": row[1],
        "reading": row[2],
        "meaning": row[3],
        "enabled": bool(row[4]),
    }


def _fetch_enabled():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, kanji, reading, meaning, enabled FROM kanji_wisdom "
            "WHERE enabled = 1 ORDER BY id"
        )
        return [_row(r) for r in cursor.fetchall()]


@router.get("/kanji/today")
async def get_kanji_today():
    """Today's quote: ``{date, id, kanji, reading, meaning}``. 404 if no quote is enabled."""
    try:
        today = _household_today()
        quote = pick_for_day(_get_cached_or_fetch(_CACHE_KEY, _fetch_enabled), today)
    except Exception as e:
        logger.error(f"Error fetching today's kanji quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    if quote is None:
        raise HTTPException(status_code=404, detail="No kanji quotes enabled")
    return {
        "date": today.isoformat(),
        "id": quote["id"],
        "kanji": quote["kanji"],
        "reading": quote["reading"],
        "meaning": quote["meaning"],
    }


@router.get("/kanji")
async def list_kanji(_perm=Depends(require_permission("kanji", "read"))):
    """Every quote, enabled or not (management view)."""
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, kanji, reading, meaning, enabled FROM kanji_wisdom ORDER BY id"
            )
            return [_row(r) for r in cursor.fetchall()]
    except pymysql.Error as e:
        logger.error(f"Error listing kanji quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kanji", status_code=201)
async def create_kanji(
    data: KanjiQuoteCreate, _perm=Depends(require_permission("kanji", "create"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO kanji_wisdom (kanji, reading, meaning, enabled) "
                "VALUES (%s, %s, %s, %s)",
                (data.kanji, data.reading, data.meaning, int(data.enabled)),
            )
            db.commit()
            new_id = cursor.lastrowid
    except pymysql.IntegrityError:
        raise HTTPException(status_code=409, detail="That kanji quote already exists")
    except pymysql.Error as e:
        logger.error(f"Error creating kanji quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    _invalidate_cache(_CACHE_KEY)
    return {"id": new_id, **data.model_dump()}


@router.put("/kanji/{quote_id}")
async def update_kanji(
    quote_id: int, data: KanjiQuoteUpdate, _perm=Depends(require_permission("kanji", "update"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE kanji_wisdom SET kanji = %s, reading = %s, meaning = %s, enabled = %s "
                "WHERE id = %s",
                (data.kanji, data.reading, data.meaning, int(data.enabled), quote_id),
            )
            db.commit()
            cursor.execute("SELECT 1 FROM kanji_wisdom WHERE id = %s", (quote_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Kanji quote not found")
    except HTTPException:
        raise
    except pymysql.IntegrityError:
        raise HTTPException(status_code=409, detail="That kanji quote already exists")
    except pymysql.Error as e:
        logger.error(f"Error updating kanji quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    _invalidate_cache(_CACHE_KEY)
    return {"id": quote_id, **data.model_dump()}


@router.delete("/kanji/{quote_id}")
async def delete_kanji(quote_id: int, _perm=Depends(require_permission("kanji", "delete"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM kanji_wisdom WHERE id = %s", (quote_id,))
            db.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Kanji quote not found")
    except HTTPException:
        raise
    except pymysql.Error as e:
        logger.error(f"Error deleting kanji quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    _invalidate_cache(_CACHE_KEY)
    return {"id": quote_id, "deleted": True}
