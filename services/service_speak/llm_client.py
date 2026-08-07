import os
import sys
import logging
import pymysql

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_connection

logger = logging.getLogger(__name__)

_claude_client = None

DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"


def get_db_connection():
    return get_connection()


def get_claude_config():
    db = get_db_connection()
    cursor = db.cursor()
    config = {}
    try:
        cursor.execute(
            "SELECT name, value FROM config WHERE name IN ('llm_api_key', 'llm_usage_limit', 'llm_model')"
        )
        for row in cursor.fetchall():
            config[row[0]] = row[1]
        return {
            "api_key": config.get("llm_api_key", ""),
            "usage_limit": int(config.get("llm_usage_limit", 10)),
            "model": config.get("llm_model") or DEFAULT_LLM_MODEL,
        }
    except pymysql.Error as e:
        logger.error(f"Database error getting Claude config: {e}")
        db.rollback()
        return {"api_key": "", "usage_limit": 10, "model": DEFAULT_LLM_MODEL}
    finally:
        db.close()


def save_claude_config(api_key=None, usage_limit=None, model=None):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        for name, value in (("llm_api_key", api_key), ("llm_usage_limit", usage_limit), ("llm_model", model)):
            if value is not None:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    (name, str(value), str(value)),
                )
        db.commit()
        return True
    except pymysql.Error as e:
        logger.error(f"Database error saving Claude config: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def _get_calls_today():
    from personality import get_environment_id

    env_id = get_environment_id()
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "SELECT llm_calls_today FROM context WHERE environment_id = %s LIMIT 1",
            (env_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except pymysql.Error as e:
        logger.error(f"Database error getting calls today: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def check_usage_limit(config=None):
    if config is None:
        config = get_claude_config()
    if not config.get("api_key"):
        return False, "No API key configured"

    calls_today = _get_calls_today()
    limit = config.get("usage_limit", 10)

    if calls_today >= limit:
        return False, f"Daily limit reached ({calls_today}/{limit})"

    return True, None


def increment_llm_calls():
    from personality import get_environment_id

    env_id = get_environment_id()
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO context (environment_id, llm_calls_today, updated_at) "
            "VALUES (%s, 1, NOW()) "
            "ON DUPLICATE KEY UPDATE llm_calls_today = llm_calls_today + 1, "
            "updated_at = NOW()",
            (env_id,),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Database error incrementing LLM calls: {e}")
        db.rollback()
    finally:
        db.close()


def _get_claude_client(api_key=None):
    global _claude_client
    if _claude_client is None:
        if api_key is None:
            api_key = get_claude_config().get("api_key")
        if api_key:
            try:
                from anthropic import Anthropic

                _claude_client = Anthropic(api_key=api_key)
            except ImportError:
                logger.error("anthropic package not installed")
                return None
    return _claude_client


def call_claude_haiku(system_prompt, user_text, config=None):
    if config is None:
        config = get_claude_config()

    if not config.get("api_key"):
        logger.warning("Claude call skipped: no API key configured")
        return None

    client = _get_claude_client(config.get("api_key"))
    if not client:
        return None

    allowed, reason = check_usage_limit(config)
    if not allowed:
        logger.warning(f"Claude call skipped: {reason}")
        return None

    try:
        response = client.messages.create(
            model=config.get("model", DEFAULT_LLM_MODEL),
            max_tokens=100,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )

        increment_llm_calls()

        return response.content[0].text.strip()

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


def reset_daily_calls():
    from personality import get_environment_id

    env_id = get_environment_id()
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO context (environment_id, llm_calls_today, updated_at) "
            "VALUES (%s, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE llm_calls_today = 0, updated_at = NOW()",
            (env_id,),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Database error resetting daily calls: {e}")
        db.rollback()
    finally:
        db.close()
