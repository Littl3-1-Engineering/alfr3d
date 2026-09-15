import logging
import time
import pymysql
from datetime import datetime, timedelta

from .db_pool import get_connection

logger = logging.getLogger("DBUtils")

_cached_states = None
_cached_user_types = None
_cached_env_name = None
_cached_env_id = None


def wait_for_db(max_attempts=30, delay=2):
    """Block until MySQL is reachable, retrying with backoff. Returns True on success."""
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            db = get_connection()
            cursor = db.cursor()
            cursor.execute("SELECT 1")
            db.close()
            logger.info(f"Database connection established (attempt {attempt})")
            return True
        except Exception as e:
            last_err = e
            logger.warning(f"Database not ready (attempt {attempt}/{max_attempts}): {e}")
            time.sleep(delay)
    logger.error(f"Database not reachable after {max_attempts} attempts: {last_err}")
    return False


def get_db_connection():
    return get_connection()


def get_env_timezone(env_name):
    """Get timezone offset in seconds from environment table."""
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("SELECT timezone FROM environment WHERE name = %s", (env_name,))
        result = cursor.fetchone()
        db.close()
        return result[0] if result and result[0] is not None else 0
    except Exception as e:
        logger.error(f"Error fetching timezone: {e}")
        return 0


def get_env_local_time(env_name):
    """Get current time adjusted to environment timezone.

    Assumes container runs in UTC and adds environment timezone offset.
    """
    timezone_seconds = get_env_timezone(env_name)
    offset_hours = timezone_seconds / 3600
    return datetime.utcnow() + timedelta(hours=offset_hours)


def get_cached_env_id(cursor, env_name):
    global _cached_env_id, _cached_env_name
    if _cached_env_id is None or _cached_env_name != env_name:
        cursor.execute("SELECT id FROM environment WHERE name = %s", (env_name,))
        data = cursor.fetchone()
        if data:
            _cached_env_id = data[0]
            _cached_env_name = env_name
    return _cached_env_id


def get_cached_states(cursor):
    global _cached_states
    if _cached_states is None:
        cursor.execute("SELECT id, state FROM states")
        _cached_states = {row[1]: row[0] for row in cursor.fetchall()}
    return _cached_states


def get_cached_user_types(cursor):
    global _cached_user_types
    if _cached_user_types is None:
        cursor.execute("SELECT id, type FROM user_types")
        _cached_user_types = {row[1]: row[0] for row in cursor.fetchall()}
    return _cached_user_types


def clear_cache():
    global _cached_states, _cached_user_types, _cached_env_id, _cached_env_name
    _cached_states = None
    _cached_user_types = None
    _cached_env_id = None
    _cached_env_name = None


def get_mute_state(env_name) -> tuple[bool, bool]:
    """Return (is_sleeping, is_empty_house) as independent signals instead of one
    collapsed bool, so a caller can react differently to each (service_speak uses
    this to still emit an event -- for the Deck phone-speech relay -- when the
    house is merely empty, while staying fully silent when it's sleeping hours).

    is_sleeping: outside the household's waking hours (the Morning..Bedtime
    routine window, via day_context).
    is_empty_house: no owner/technoking/resident currently online to hear it.
    Checked independently of is_sleeping (not short-circuited) so a caller that
    bypasses the sleeping gate still gets an accurate empty-house read.
    """
    if not env_name:
        logger.error("Environment name not provided")
        return False, False

    # "Are we inside waking hours" is the Morning..Bedtime routine window -- now
    # owned by day_context so every consumer (this, service_speak, the daemon's
    # idle-quip wind-down, the LLM prompt) reads one definition. Imported here
    # rather than at module scope to avoid a common<->day_context import cycle.
    from .day_context import get_day_context

    is_sleeping = not get_day_context(env_name).is_waking_hours
    if is_sleeping:
        logger.info("Alfr3d should be quiet while we're sleeping")

    try:
        db = get_db_connection()
        cursor = db.cursor()
    except pymysql.Error as e:
        logger.error(f"Database connection error: {e}")
        return is_sleeping, False

    try:
        cursor.execute(
            """
            SELECT u.username
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            WHERE s.state = 'online' AND ut.type IN ('owner', 'technoking', 'resident')
            AND u.username != 'unknown'
            """
        )
        online_users = cursor.fetchall()
        db.close()

        if not online_users:
            logger.info("Alfr3d should be quiet when no worthy ears are around")
            return is_sleeping, True

        logger.info("Alfr3d is free to speak during this time of day")
        logger.info("Alfr3d has worthy listeners:")
        for user in online_users:
            logger.info(f"    - {user[0]}")

        return is_sleeping, False

    except Exception as e:
        logger.error(f"Error in check_mute: {e}")
        try:
            db.close()
        except Exception:
            pass
        return is_sleeping, False


def check_mute_optimized(env_name) -> bool:
    """Return True when Alfr3d should stay quiet: outside the household's waking
    hours or with no owner/technoking/resident currently online to hear it.
    See get_mute_state() for the two signals broken out separately.
    """
    is_sleeping, is_empty_house = get_mute_state(env_name)
    return is_sleeping or is_empty_house


def get_lookup_ids(cursor, state_name=None, user_type_name=None, env_name=None):
    """
    Get multiple lookup IDs in a single call.
    Returns dict with state_id, type_id, env_id if requested.
    """
    results = {}
    placeholders = []
    tables = []

    if state_name:
        placeholders.append(state_name)
        tables.append(("state", "states", "state", "%s"))
    if user_type_name:
        placeholders.append(user_type_name)
        tables.append(("type_id", "user_types", "type", "%s"))
    if env_name:
        placeholders.append(env_name)
        tables.append(("env_id", "environment", "name", "%s"))

    for key, table, col, placeholder in tables:
        cursor.execute(
            f"SELECT id FROM {table} WHERE {col} = {placeholder}",
            (
                placeholders[
                    len(
                        [
                            t
                            for t in tables
                            if tables.index(t) < tables.index((key, table, col, placeholder))
                        ]
                    )
                ],
            ),
        )
        data = cursor.fetchone()
        if data:
            results[key] = data[0]

    return results
