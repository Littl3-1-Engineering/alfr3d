"""Launcher-reported context signals: surface state, attention telemetry, and
situational-awareness card interactions.

Deliberately separate from routes/devices.py or routes/music.py: this isn't
about a specific ALFR3D-owned resource, it's consumers (the React dashboard,
the Nexus Launcher) telling the backend about their own UI state/usage so
alfr3ddaemon.py's DISPLAY_RULES checks can react to it --
check_cross_surface_continuity() (surface state),
check_attention_focus()/check_wind_down_signal() (attention telemetry), and
decide_displays()'s suppression pass (card interactions).
See todo/todo_cross_surface_continuity.md, todo/todo_attention_telemetry.md,
todo/todo_card_feedback_loop.md.
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
    switch count, per-category dwell time) into `config`, and also append it to
    `attention_telemetry_history` (SA-2) so check_attention_focus()/check_wind_down_signal() can
    compare against this household's own rolling distribution instead of only a fixed threshold.
    The `config` snapshot is unchanged -- this is purely an additional destination."""
    try:
        data = data or {}
        unlock_count = int(data.get("unlock_count", 0))
        switch_count = int(data.get("switch_count", 0))
        dwell_by_category_ms = data.get("dwell_by_category_ms") or {}
        window_start_ms = data.get("window_start_ms")
        window_end_ms = data.get("window_end_ms")
        reported_at = datetime.now(timezone.utc)
        snapshot = {
            "unlock_count": unlock_count,
            "switch_count": switch_count,
            "dwell_by_category_ms": dwell_by_category_ms,
            "window_start_ms": window_start_ms,
            "window_end_ms": window_end_ms,
            "reported_at": reported_at.isoformat(),
        }
        with db_connection() as db:
            cursor = db.cursor()
            _upsert_config_json(cursor, ATTENTION_TELEMETRY_CONFIG_KEY, snapshot)
            cursor.execute(
                "INSERT INTO attention_telemetry_history "
                "(unlock_count, switch_count, dwell_by_category_ms, window_start_ms, "
                "window_end_ms, reported_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    unlock_count,
                    switch_count,
                    orjson.dumps(dwell_by_category_ms).decode("utf-8"),
                    window_start_ms,
                    window_end_ms,
                    reported_at,
                ),
            )
            db.commit()
        return {"message": "Attention telemetry recorded"}
    except Exception as e:
        logger.error(f"Error recording attention telemetry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_CARD_INTERACTION_ACTIONS = {"shown", "tapped", "dismissed", "expired"}


@router.post("/context/card-interaction")
async def report_card_interaction(
    data: dict = None, _perm=Depends(require_permission("context", "card_interaction"))
):
    """Record a `card_interactions` row for one situational-awareness card
    (SA-1). Card identity is `(rule_id, subject_key)` -- see
    todo/todo_card_feedback_loop.md for why that's the identity instead of
    `(mode, content_hash)`. `rule_id` is the DISPLAY_RULES id
    (`alfr3ddaemon.py`), not the card's own `mode` field -- the two aren't
    always the same (`check_gatherings`/rule id "music" and
    `check_now_playing`/rule id "now_playing" both stamp `"mode": "music"` on
    their card).

    `shown` must be reported by the consumer only after actually rendering
    the card (i.e. after any client-side truncation like
    `MAX_DISPLAY_CARDS`) -- never assumed by the daemon, which has no way to
    know what a truncated-away card's fate was.
    """
    try:
        data = data or {}
        rule_id = data.get("rule_id")
        action = data.get("action")
        if not rule_id or action not in _CARD_INTERACTION_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"rule_id and one of {sorted(_CARD_INTERACTION_ACTIONS)} are required",
            )
        subject_key = data.get("subject_key") or ""
        user_id = data.get("user_id")
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO card_interactions "
                "(rule_id, subject_key, action, user_id, occurred_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (rule_id, subject_key, action, user_id, datetime.now(timezone.utc)),
            )
            db.commit()
        return {"message": "Card interaction recorded"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording card interaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))
