"""Launcher-reported context signals -- currently just surface state.

Deliberately separate from routes/devices.py or routes/music.py: this isn't
about a specific ALFR3D-owned resource, it's the Nexus Launcher telling the
backend about its own UI state (which surface is active, whether a terminal
session is open) so alfr3ddaemon.check_cross_surface_continuity() can offer
a "pick up where you left off" resume. See todo/todo_cross_surface_continuity.md.
"""

import logging
from datetime import datetime, timezone

import orjson
from fastapi import APIRouter, Depends, HTTPException

from common import db_connection
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["context"])

# Mirrors alfr3ddaemon.SURFACE_STATE_CONFIG_KEY -- kept in sync manually since
# service_api and service_daemon are separate deployables with no shared
# constants module today (same as NOW_PLAYING_CONFIG_KEY's own precedent).
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"


@router.post("/context/surface-state")
async def report_surface_state(
    data: dict = None, _perm=Depends(require_permission("context", "surface_state"))
):
    """Upsert the launcher's currently-active surface into `config`, using the
    same UPDATE-then-INSERT-if-0-rows pattern as spotify_utils.save_spotify_credentials()
    and alfr3ddaemon._write_now_playing_config()."""
    try:
        data = data or {}
        state = {
            "active_surface": data.get("active_surface"),
            "terminal_session_active": bool(data.get("terminal_session_active", False)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        value = orjson.dumps(state).decode("utf-8")

        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = %s",
                (value, SURFACE_STATE_CONFIG_KEY),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES (%s, %s)",
                    (SURFACE_STATE_CONFIG_KEY, value),
                )
            db.commit()
        return {"message": "Surface state recorded"}
    except Exception as e:
        logger.error(f"Error recording surface state: {e}")
        raise HTTPException(status_code=500, detail=str(e))
