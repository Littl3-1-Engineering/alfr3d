import os
import logging

import pymysql

logger = logging.getLogger(__name__)

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

_claude_client = None


def get_db_connection():
    return pymysql.connect(
        host=MYSQL_DATABASE,
        user=MYSQL_USER,
        passwd=MYSQL_PSWD,
        db=MYSQL_DB,
    )


def get_claude_config():
    db = get_db_connection()
    cursor = db.cursor()
    config = {}
    try:
        cursor.execute(
            "SELECT name, value FROM config WHERE name IN ('llm_api_key', 'llm_usage_limit')"
        )
        for row in cursor.fetchall():
            config[row[0]] = row[1]
        return {
            "api_key": config.get("llm_api_key", ""),
            "usage_limit": int(config.get("llm_usage_limit", 10)),
        }
    except pymysql.Error as e:
        logger.error(f"Database error getting Claude config: {e}")
        db.rollback()
        return {"api_key": "", "usage_limit": 10}
    finally:
        db.close()


def save_claude_config(api_key=None, usage_limit=None):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        if api_key is not None:
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = 'llm_api_key'",
                (api_key,),
            )
        if usage_limit is not None:
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = 'llm_usage_limit'",
                (str(usage_limit),),
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


def check_usage_limit():
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
            "UPDATE context SET llm_calls_today = llm_calls_today + 1, "
            "updated_at = NOW() WHERE environment_id = %s",
            (env_id,),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Database error incrementing LLM calls: {e}")
        db.rollback()
    finally:
        db.close()


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        config = get_claude_config()
        api_key = config.get("api_key")
        if api_key:
            try:
                from anthropic import Anthropic

                _claude_client = Anthropic(api_key=api_key)
            except ImportError:
                logger.error("anthropic package not installed")
                return None
    return _claude_client


def call_claude_haiku(system_prompt, user_text):
    client = _get_claude_client()
    if not client:
        return None

    allowed, reason = check_usage_limit()
    if not allowed:
        logger.warning(f"Claude call skipped: {reason}")
        return None

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
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
            "UPDATE context SET llm_calls_today = 0, updated_at = NOW() "
            "WHERE environment_id = %s",
            (env_id,),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Database error resetting daily calls: {e}")
        db.rollback()
    finally:
        db.close()
