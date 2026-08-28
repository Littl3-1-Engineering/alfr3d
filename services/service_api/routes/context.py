"""Launcher-reported context signals: surface state and attention telemetry.

Deliberately separate from routes/devices.py or routes/music.py: this isn't
about a specific ALFR3D-owned resource, it's the Nexus Launcher telling the
backend about its own UI state/usage so alfr3ddaemon.py's DISPLAY_RULES
checks can react to it -- check_cross_surface_continuity() (surface state)
and check_attention_focus()/check_wind_down_signal() (attention telemetry).
See todo/todo_cross_surface_continuity.md, todo/todo_attention_telemetry.md.
"""

import logging
from datetime import datetime, timezone

import orjson
from fastapi import APIRouter, Depends, HTTPException

from common import db_connection
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["context"])

# Mirrors alfr3ddaemon.SURFACE_STATE_CONFIG_KEY / ATTENTION_TELEMETRY_CONFIG_KEY -- kept in sync
# manually since service_api and service_daemon are separate deployables with no shared
# constants module today (same as NOW_PLAYING_CONFIG_KEY's own precedent).
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"
ATTENTION_TELEMETRY_CONFIG_KEY = "launcher_attention_telemetry"


def _upsert_config_json(cursor, key, value_dict):
    """UPDATE-then-INSERT-if-0-rows upsert of a JSON blob into `config`, the same pattern
    spotify_utils.save_spotify_credentials() and alfr3ddaemon._write_now_playing_config() use.
    Factored out here now that this file has two callers."""
    value = orjson.dumps(value_dict).decode("utf-8")
    cursor.execute("UPDATE config SET value = %s WHERE name = %s", (value, key))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO config (name, value) VALUES (%s, %s)", (key, value))


@router.post("/context/surface-state")
async def report_surface_state(
    data: dict = None, _perm=Depends(require_permission("context", "surface_state"))
):
    """Upsert the launcher's currently-active surface into `config`."""
    try:
        data = data or {}
        state = {
            "active_surface": data.get("active_surface"),
            "terminal_session_active": bool(data.get("terminal_session_active", False)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with db_connection() as db:
            cursor = db.cursor()
            _upsert_config_json(cursor, SURFACE_STATE_CONFIG_KEY, state)
            db.commit()
        return {"message": "Surface state recorded"}
    except Exception as e:
        logger.error(f"Error recording surface state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/attention-telemetry")
async def report_attention_telemetry(
    data: dict = None, _perm=Depends(require_permission("context", "attention_telemetry"))
):
    """Upsert the launcher's most recent attention-telemetry snapshot (unlock count, window
    switch count, per-category dwell time) into `config`. Rolling-window semantics on the
    launcher side (see AttentionTelemetryStore.snapshotAndReset() in alfr3d_deck) -- this just
    persists whatever the most recent report said, no history kept here."""
    try:
        data = data or {}
        snapshot = {
            "unlock_count": int(data.get("unlock_count", 0)),
            "switch_count": int(data.get("switch_count", 0)),
            "dwell_by_category_ms": data.get("dwell_by_category_ms") or {},
            "window_start_ms": data.get("window_start_ms"),
            "window_end_ms": data.get("window_end_ms"),
            "reported_at": datetime.now(timezone.utc).isoformat(),
        }
        with db_connection() as db:
            cursor = db.cursor()
            _upsert_config_json(cursor, ATTENTION_TELEMETRY_CONFIG_KEY, snapshot)
            db.commit()
        return {"message": "Attention telemetry recorded"}
    except Exception as e:
        logger.error(f"Error recording attention telemetry: {e}")
        raise HTTPException(status_code=500, detail=str(e))
