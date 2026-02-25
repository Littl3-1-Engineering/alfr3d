import os
import logging
import pymysql

logger = logging.getLogger("DBUtils")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mysql")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")
MYSQL_USER = os.environ.get("MYSQL_USER", "user")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "password")

_cached_states = None
_cached_user_types = None
_cached_env_name = None
_cached_env_id = None


def get_db_connection():
    return pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)


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


def check_mute_optimized(env_name) -> bool:
    """
    Optimized check_mute that combines multiple queries into fewer database calls.
    """
    if not env_name:
        logger.error("Environment name not provided")
        return False

    try:
        db = get_db_connection()
        cursor = db.cursor()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return False

    try:
        cursor.execute(
            """
            SELECT r_morning.time as morning_time, r_bed.time as bed_time
            FROM environment e
            JOIN routines r_morning ON e.id = r_morning.environment_id
            AND r_morning.name = 'Morning'
            JOIN routines r_bed ON e.id = r_bed.environment_id AND r_bed.name = 'Bedtime'
            WHERE e.name = %s
            """,
            (env_name,),
        )
        routine_times = cursor.fetchone()

        if not routine_times:
            logger.error("Morning or Bedtime routine not found")
            db.close()
            return False

        morning_time, bed_time = routine_times
        cur_time = __import__("datetime").datetime.now()
        mor_time = cur_time.replace(
            hour=int(morning_time.seconds / 3600),
            minute=int((morning_time.seconds // 60) % 60),
        )
        end_time = cur_time.replace(
            hour=int(bed_time.seconds / 3600), minute=int((bed_time.seconds // 60) % 60)
        )

        if cur_time <= mor_time or cur_time >= end_time:
            logger.info("Alfr3d should be quiet while we're sleeping")
            db.close()
            return True

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

        if not online_users:
            logger.info("Alfr3d should be quiet when no worthy ears are around")
            db.close()
            return True

        logger.info("Alfr3d is free to speak during this time of day")
        logger.info("Alfr3d has worthy listeners:")
        for user in online_users:
            logger.info(f"    - {user[0]}")

        db.close()
        return False

    except Exception as e:
        logger.error(f"Error in check_mute: {e}")
        try:
            db.close()
        except Exception:
            pass
        return False


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
