"""Shared state, helpers, and dependencies for ALFR3D API routes."""

import os
import sys
import logging
import subprocess
from typing import Any, Dict, List

import orjson

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import db_connection, get_producer as _get_producer, get_cache

logger = logging.getLogger("ApiLog")

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PSWD = os.environ["MYSQL_PSWD"]
MYSQL_DB = os.environ["MYSQL_NAME"]
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ALFR3D_ENV_NAME = os.environ["ALFR3D_ENV_NAME"]


def get_producer():
    return _get_producer(use_json_serializer=True)


_cache = get_cache()
_cache_ttl = 300


def _get_cached_or_fetch(key, fetch_fn, ttl=_cache_ttl):
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = fetch_fn()
    _cache.set(key, result, ttl)
    return result


def _invalidate_cache(key):
    _cache.invalidate(key)


def _invalidate_cache_pattern(pattern):
    """Invalidate all cache keys matching a pattern (e.g., 'api:devices:*')."""
    return _cache.invalidate_pattern(pattern)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[Any] = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: str, data: Any):
        for connection in self.active_connections:
            try:
                await connection.send_json({"event": event, "data": data})
            except Exception:
                pass


manager = ConnectionManager()
recent_events: List[Any] = []
recent_sa: List[Any] = []


docker_available = False
try:
    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    result = subprocess.run(
        ["docker", "version"], capture_output=True, text=True, timeout=5, env=env
    )
    if result.returncode == 0:
        docker_available = True
        logger.info("Docker CLI is available via socket")
    else:
        logger.warning("Docker CLI not available")
except subprocess.SubprocessError as e:
    logger.warning(f"Docker check failed: {str(e)}")


def normalize_time(time_str):
    if not time_str:
        return time_str
    if len(time_str) == 8:
        return time_str
    if len(time_str) == 5 and ":" in time_str:
        parts = time_str.split(":")
        hour = parts[0].zfill(2)
        return f"{hour}:{parts[1]}:00"
    return time_str


def run_docker_command(command: List[str], env: Dict[str, str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, env=env)
    if result.returncode != 0:
        logger.error(f"Docker command failed: {result.stderr}")
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    return result.stdout


def parse_docker_json(output: str) -> List[Dict[str, Any]]:
    containers = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:
                containers.append(orjson.loads(line))
            except orjson.JSONDecodeError as e:
                logger.warning(f"Error parsing JSON: {e}")
    return containers


def get_environment_id():
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            row = cursor.fetchone()
            return row[0] if row else 1
    except Exception:
        return 1


def _fetch_quips(category=None):
    with db_connection() as db:
        cursor = db.cursor()
        if category:
            cursor.execute(
                "SELECT id, type, category, quips FROM quips WHERE category = %s", (category,)
            )
        else:
            cursor.execute("SELECT id, type, category, quips FROM quips")
        quips = [
            {"id": row[0], "type": row[1], "category": row[2], "quips": row[3]}
            for row in cursor.fetchall()
        ]
        return quips


def _fetch_routines():
    import pymysql

    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT id, name, time, enabled, triggered, recurrence, actions, triggers, "
            "conditions, last_run "
            "FROM routines WHERE environment_id = (SELECT id FROM environment WHERE name = %s) "
            "ORDER BY time",
            (ALFR3D_ENV_NAME,),
        )
        routines = cursor.fetchall()
        for routine in routines:
            if routine.get("actions"):
                routine["actions"] = orjson.loads(routine["actions"])
            if routine.get("triggers"):
                routine["triggers"] = orjson.loads(routine["triggers"])
            if routine.get("conditions"):
                routine["conditions"] = orjson.loads(routine["conditions"])
            if routine.get("time"):
                routine["time"] = str(routine["time"])
            if routine.get("last_run"):
                routine["last_run"] = str(routine["last_run"])
        return routines


def _fetch_personality():
    import pymysql

    env_id = get_environment_id()
    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT * FROM personality WHERE type = 'current' AND "
            "(environment_id = %s OR environment_id IS NULL) "
            "ORDER BY environment_id DESC LIMIT 1",
            (env_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "name": row["name"],
                "sarcasm": float(row["sarcasm"]),
                "formality": float(row["formality"]),
                "warmth": float(row["warmth"]),
                "patience": float(row["patience"]),
                "linguistic_style": row["linguistic_style"] or "",
                "forbidden_words": row["forbidden_words"] or "",
                "verbal_tics": row["verbal_tics"] or "",
            }
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Personality not found")


def _fetch_personality_presets():
    import pymysql

    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM personality WHERE type = 'preset' ORDER BY name")
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "sarcasm": float(row["sarcasm"]),
                "formality": float(row["formality"]),
                "warmth": float(row["warmth"]),
                "patience": float(row["patience"]),
                "linguistic_style": row["linguistic_style"] or "",
                "forbidden_words": row["forbidden_words"] or "",
                "verbal_tics": row["verbal_tics"] or "",
            }
            for row in rows
        ]


def _fetch_devices():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, u.username, d.last_online,
                   d.position_x, d.position_y, d.stream_url
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            """,
            (ALFR3D_ENV_NAME,),
        )
        devices = [
            {
                "id": row[0],
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "user": row[6],
                "last_online": row[7].isoformat() if row[7] else None,
                "position": (
                    {"x": row[8], "y": row[9]}
                    if row[8] is not None and row[9] is not None
                    else None
                ),
                # Never expose the raw RTSP URL (embedded credentials) via this endpoint --
                # it's broadcast to every connected websocket client, not just the requester.
                "has_stream": row[10] is not None,
            }
            for row in cursor.fetchall()
        ]
        return devices


def _fetch_users():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT u.id, u.username, u.email, u.about_me, s.state, ut.type,
                   u.last_online, u.created_at
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            JOIN environment e ON u.environment_id = e.id
            WHERE u.username NOT IN ('unknown', 'alfr3d') AND e.name = %s
            """,
            (ALFR3D_ENV_NAME,),
        )
        users = [
            {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "about_me": row[3],
                "state": row[4],
                "type": row[5],
                "last_online": row[6].isoformat() if row[6] else None,
                "created_at": row[7].isoformat() if row[7] else None,
            }
            for row in cursor.fetchall()
        ]
        return users


def _fetch_weather():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT name, city, state, country, low, high, temperature, description, "
            "sunrise, sunset, pressure, pressure_trend, humidity, timezone "
            "FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "city": row[1],
                "state": row[2],
                "country": row[3],
                "low": row[4],
                "high": row[5],
                "temperature": row[6],
                "description": row[7],
                "sunrise": row[8].isoformat() if row[8] else None,
                "sunset": row[9].isoformat() if row[9] else None,
                "pressure": row[10],
                "pressure_trend": row[11],
                "humidity": row[12],
                "timezone": row[13],
            }
        return None


def _fetch_environment():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "temperature, description, sunrise, sunset, pressure, pressure_trend, "
            "humidity, manual_override, manual_location_override, subjective_feel, timezone "
            "FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "latitude": row[2],
                "longitude": row[3],
                "city": row[4],
                "state": row[5],
                "country": row[6],
                "ip": row[7],
                "temp_min": row[8],
                "temp_max": row[9],
                "temperature": row[10],
                "description": row[11],
                "sunrise": row[12].isoformat() if row[12] else None,
                "sunset": row[13].isoformat() if row[13] else None,
                "pressure": row[14],
                "pressure_trend": row[15],
                "humidity": row[16],
                "manual_override": row[17],
                "manual_location_override": row[18],
                "subjective_feel": row[19],
                "timezone": row[20],
            }
        return None


def _fetch_context():
    import pymysql

    env_id = get_environment_id()
    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM context WHERE environment_id = %s LIMIT 1", (env_id,))
        row = cursor.fetchone()
        if row:
            return {
                "repeat_count": row["repeat_count"],
                "hour": row["hour"],
                "weather": row["weather"] or "clear",
                "mood": row["mood"],
                "last_error_count": row["last_error_count"],
                "llm_calls_today": row["llm_calls_today"],
            }
    return None


def _fetch_llm_config():
    """Backs the unauthenticated GET /personality/llm-config route (GETs stay public per the
    read-only-for-anonymous convention -- see auth/dependencies.py). Never returns the actual
    key: only whether one is configured, so the Anthropic API key can't be read off the network
    by anyone who can reach the API. The real value is only ever read server-side by
    service_speak/llm_client.py's get_claude_config()."""
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT name, value FROM config "
            "WHERE name IN ('llm_api_key', 'llm_usage_limit', 'llm_model')"
        )
        rows = cursor.fetchall()
        config = {row[0]: row[1] for row in rows}
        return {
            "api_key_set": bool(config.get("llm_api_key")),
            "usage_limit": int(config.get("llm_usage_limit", 10)),
            "model": config.get("llm_model") or "claude-haiku-4-5-20251001",
        }
