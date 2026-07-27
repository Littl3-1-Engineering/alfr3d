"""Shared state, helpers, and dependencies for ALFR3D API routes."""

import os
import sys
import logging
import subprocess
from typing import Any, Dict, List

import orjson

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_connection, get_producer as _get_producer, get_cache

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
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        row = cursor.fetchone()
        db.close()
        return row[0] if row else 1
    except Exception:
        return 1


def _fetch_quips():
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("SELECT id, type, quips FROM quips")
    quips = [{"id": row[0], "type": row[1], "quips": row[2]} for row in cursor.fetchall()]
    db.close()
    return quips


def _fetch_routines():
    import pymysql
    db = get_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    cursor.execute(
        "SELECT id, name, time, enabled, triggered, recurrence, actions, last_run "
        "FROM routines WHERE environment_id = (SELECT id FROM environment WHERE name = %s) "
        "ORDER BY time",
        (ALFR3D_ENV_NAME,),
    )
    routines = cursor.fetchall()
    for routine in routines:
        if routine.get("actions"):
            routine["actions"] = orjson.loads(routine["actions"])
        if routine.get("time"):
            routine["time"] = str(routine["time"])
        if routine.get("last_run"):
            routine["last_run"] = str(routine["last_run"])
    db.close()
    return routines


def _fetch_personality():
    import pymysql
    env_id = get_environment_id()
    db = get_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    cursor.execute(
        "SELECT * FROM personality WHERE type = 'current' AND "
        "(environment_id = %s OR environment_id IS NULL) "
        "ORDER BY environment_id DESC LIMIT 1",
        (env_id,),
    )
    row = cursor.fetchone()
    db.close()
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
    db = get_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM personality WHERE type = 'preset' ORDER BY name")
    rows = cursor.fetchall()
    db.close()
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
