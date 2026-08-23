"""Personality management routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException
import pymysql

from dependencies import (
    db_connection,
    _get_cached_or_fetch,
    _invalidate_cache,
    get_environment_id,
    ALFR3D_ENV_NAME,
)
from models import PersonalityUpdate, ContextUpdate, LLMConfigUpdate, PresetApply
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["personality"])


@router.get("/personality")
async def get_personality():
    try:
        from dependencies import _fetch_personality

        return _get_cached_or_fetch("personality:current", _fetch_personality)
    except pymysql.Error as e:
        logger.error(f"Error fetching personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/personality")
async def update_personality(
    data: PersonalityUpdate, _perm=Depends(require_permission("personality", "update"))
):
    try:
        env_id = get_environment_id()
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE personality SET "
                "sarcasm = %s, formality = %s, warmth = %s, patience = %s, "
                "linguistic_style = %s, forbidden_words = %s, verbal_tics = %s, "
                "name = %s, environment_id = %s "
                "WHERE type = 'current' AND (environment_id = %s OR environment_id IS NULL) "
                "ORDER BY environment_id DESC LIMIT 1",
                (
                    data.sarcasm,
                    data.formality,
                    data.warmth,
                    data.patience,
                    data.linguistic_style,
                    data.forbidden_words,
                    data.verbal_tics,
                    data.name,
                    env_id,
                    env_id,
                ),
            )
            db.commit()
        _invalidate_cache("personality:current")
        return {"message": "Personality updated"}
    except Exception as e:
        logger.error(f"Error updating personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/personality/presets")
async def get_personality_presets():
    try:
        from dependencies import _fetch_personality_presets

        return _get_cached_or_fetch("personality:presets", _fetch_personality_presets)
    except Exception as e:
        logger.error(f"Error fetching presets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/personality/apply-preset")
async def apply_personality_preset(
    data: PresetApply, _perm=Depends(require_permission("personality", "apply_preset"))
):
    try:
        env_id = get_environment_id()
        with db_connection() as db:
            cursor = db.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                "SELECT * FROM personality WHERE type = 'preset' AND name = %s",
                (data.preset,),
            )
            preset = cursor.fetchone()
            if not preset:
                raise HTTPException(status_code=404, detail="Preset not found")

            cursor.execute(
                "UPDATE personality SET "
                "sarcasm = %s, formality = %s, warmth = %s, patience = %s, "
                "linguistic_style = %s, forbidden_words = %s, verbal_tics = %s, "
                "name = %s, environment_id = %s "
                "WHERE type = 'current' AND (environment_id = %s OR environment_id IS NULL) "
                "ORDER BY environment_id DESC LIMIT 1",
                (
                    preset["sarcasm"],
                    preset["formality"],
                    preset["warmth"],
                    preset["patience"],
                    preset["linguistic_style"],
                    preset["forbidden_words"],
                    preset["verbal_tics"],
                    preset["name"],
                    env_id,
                    env_id,
                ),
            )
            db.commit()
        _invalidate_cache("personality:current")
        return {"message": f"Applied preset: {data.preset}"}
    except Exception as e:
        logger.error(f"Error applying preset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/personality/context")
async def get_personality_context():
    try:
        from dependencies import _fetch_context

        ctx = _get_cached_or_fetch(
            f"personality:context:{ALFR3D_ENV_NAME}", _fetch_context, ttl=300
        )
        if ctx:
            return ctx
        raise HTTPException(status_code=404, detail="Context not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/personality/context")
async def update_personality_context(
    data: ContextUpdate, _perm=Depends(require_permission("personality", "update_context"))
):
    try:
        env_id = get_environment_id()
        with db_connection() as db:
            cursor = db.cursor()
            updates = []
            values = []
            allowed_fields = ["repeat_count", "hour", "weather", "mood", "last_error_count"]
            for field in allowed_fields:
                value = getattr(data, field, None)
                if value is not None:
                    updates.append(f"{field} = %s")
                    values.append(value)
            if updates:
                values.append(env_id)
                cursor.execute(
                    f"UPDATE context SET {', '.join(updates)} WHERE environment_id = %s",
                    values,
                )
                db.commit()
        _invalidate_cache(f"personality:context:{ALFR3D_ENV_NAME}")
        return {"message": "Context updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/personality/llm-config")
async def get_llm_config():
    try:
        from dependencies import _fetch_llm_config

        return _get_cached_or_fetch("personality:llm-config", _fetch_llm_config, ttl=600)
    except pymysql.Error as e:
        logger.error(f"Error fetching LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/personality/llm-config")
async def update_llm_config(
    data: LLMConfigUpdate, _perm=Depends(require_permission("personality", "update_llm_config"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            if data.api_key is not None:
                cursor.execute(
                    "UPDATE config SET value = %s WHERE name = 'llm_api_key'",
                    (data.api_key,),
                )
            if data.usage_limit is not None:
                cursor.execute(
                    "UPDATE config SET value = %s WHERE name = 'llm_usage_limit'",
                    (str(data.usage_limit),),
                )
            if data.model is not None:
                cursor.execute(
                    "UPDATE config SET value = %s WHERE name = 'llm_model'",
                    (data.model,),
                )
            db.commit()
        _invalidate_cache("personality:llm-config")
        return {"message": "LLM config updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
