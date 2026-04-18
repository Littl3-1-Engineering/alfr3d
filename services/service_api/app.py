"""REST API service for ALFR3D using FastAPI."""

import asyncio
import os
import sys
import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import orjson
import pymysql
import requests
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_connection, get_producer as _get_producer, get_cache
from tree_of_alfr3d import project_tree_router, start_file_watcher_task, set_manager

CURRENT_PATH = os.path.dirname(__file__)

logger = logging.getLogger("ApiLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

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
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
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


async def consume_events():
    try:
        logger.info(f"Event consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "event-stream", bootstrap_servers=KAFKA_URL, auto_offset_reset="latest"
        )
        logger.info("Connected to Kafka event-stream topic")
        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        logger.info("Polling for event message")
                        try:
                            data = orjson.loads(message.value)
                            if isinstance(data, list):
                                recent_events.extend(data)
                            else:
                                recent_events.append(data)
                            recent_events[:] = recent_events[-20:]
                            logger.info(f"Received events: {data}")
                            await manager.broadcast("events", recent_events)
                            events_to_send = data if isinstance(data, list) else [data]
                            for event in events_to_send:
                                try:
                                    headers = {"Content-Type": "application/json"}
                                    url = "https://ntfy.sh/alfr3d-event-stream"
                                    requests.post(url, json=event, headers=headers)
                                except Exception as e:
                                    logger.error(f"Failed to send event to nfty.sh: {e}")
                        except orjson.JSONDecodeError as e:
                            logger.error(f"Error processing event message: {str(e)}")
            await asyncio.sleep(0.1)
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for events: {str(e)}")


async def consume_sa():
    try:
        logger.info(f"SA consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "situational-awareness",
            bootstrap_servers=KAFKA_URL,
            auto_offset_reset="latest",
        )
        logger.info("Connected to Kafka situational-awareness topic")
        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        logger.info("Polling for SA message")
                        try:
                            data = orjson.loads(message.value)
                            recent_sa.clear()
                            if isinstance(data, list):
                                recent_sa.extend(data)
                            else:
                                recent_sa.append(data)
                            logger.info(f"Received SA: {data}")
                            await manager.broadcast("situational_awareness", recent_sa)
                        except orjson.JSONDecodeError as e:
                            logger.error(f"Error processing SA message: {str(e)}")
            await asyncio.sleep(0.1)
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for SA: {str(e)}")


class UserCreate(BaseModel):
    name: str
    type: str
    email: Optional[str] = ""
    about_me: Optional[str] = ""


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    about_me: Optional[str] = None
    type: Optional[str] = None


class DeviceCreate(BaseModel):
    name: str
    type: str
    ip: Optional[str] = "10.0.0.125"
    mac: Optional[str] = "00:00:00:00:00:00"
    user: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None
    type: Optional[str] = None
    user: Optional[str] = None
    position: Optional[Dict[str, float]] = None


class QuipCreate(BaseModel):
    type: str
    quips: str


class QuipUpdate(BaseModel):
    type: str
    quips: str


class EnvironmentUpdate(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    ip: Optional[str] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    description: Optional[str] = None
    pressure: Optional[float] = None
    humidity: Optional[float] = None
    subjective_feel: Optional[str] = None


class RoutineCreate(BaseModel):
    name: str
    time: str = "08:00:00"
    enabled: int = 1
    recurrence: str = "daily"
    actions: List[Dict[str, Any]] = []


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    time: Optional[str] = None
    enabled: Optional[int] = None
    recurrence: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None


class PersonalityUpdate(BaseModel):
    sarcasm: Optional[float] = 0.5
    formality: Optional[float] = 0.5
    warmth: Optional[float] = 0.5
    patience: Optional[float] = 1.0
    linguistic_style: Optional[str] = ""
    forbidden_words: Optional[str] = ""
    verbal_tics: Optional[str] = ""
    name: Optional[str] = "Custom"


class ContextUpdate(BaseModel):
    repeat_count: Optional[int] = None
    hour: Optional[int] = None
    weather: Optional[str] = None
    mood: Optional[str] = None
    last_error_count: Optional[int] = None


class LLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    usage_limit: Optional[int] = None


class HAControl(BaseModel):
    command: str
    params: Dict[str, Any] = {}


class HAConfig(BaseModel):
    ha_url: str
    ha_token: str


class STControl(BaseModel):
    command: str
    capability: str = "switch"
    args: List[Any] = []


class STConfig(BaseModel):
    st_pat: str


class IoTProvider(BaseModel):
    provider: str


class IOTDeviceControl(BaseModel):
    command: str
    params: Dict[str, Any] = {}


class PresetApply(BaseModel):
    preset: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    asyncio.create_task(consume_events())
    asyncio.create_task(consume_sa())
    asyncio.create_task(start_file_watcher_task())
    yield


app = FastAPI(title="ALFR3D API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(project_tree_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/users")
async def get_users(online: bool = Query(False)):
    try:
        logger.info(f"Connecting to MySQL at {MYSQL_DATABASE} as {MYSQL_USER}")
        db = get_connection()
        cursor = db.cursor()
        if online:
            cursor.execute(
                """
                SELECT u.id, u.username, u.email, u.about_me, s.state, ut.type,
                       u.last_online, u.created_at
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                JOIN environment e ON u.environment_id = e.id
                WHERE s.state = 'online' AND u.username NOT IN ('unknown', 'alfr3d')
                      AND e.name = %s
            """,
                (ALFR3D_ENV_NAME,),
            )
        else:
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
        users = []
        for row in cursor.fetchall():
            users.append(
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
            )
        db.close()
        logger.info(f"Returning {len(users)} users")
        await manager.broadcast("users", users)
        return users
    except pymysql.Error as e:
        logger.error(f"Error fetching users: {str(e)}")
        mock_users = (
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
            ]
            if online
            else [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "offline",
                    "last_online": "",
                },
            ]
        )
        return mock_users


@app.post("/api/users", status_code=201)
async def create_user(data: UserCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM states WHERE state = 'offline'")
        state_row = cursor.fetchone()
        if not state_row:
            raise HTTPException(status_code=500, detail="Offline state not found")
        state_id = state_row[0]
        cursor.execute("SELECT id FROM user_types WHERE type = %s", (data.type,))
        type_row = cursor.fetchone()
        if not type_row:
            raise HTTPException(status_code=400, detail="Invalid user type")
        type_id = type_row[0]
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            raise HTTPException(status_code=500, detail="Environment not found")
        env_id = env_row[0]
        cursor.execute(
            "INSERT INTO user (username, email, about_me, created_at, state, type, environment_id) "
            "VALUES (%s, %s, %s, NOW(), %s, %s, %s)",
            (data.name, data.email, data.about_me, state_id, type_id, env_id),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return {"id": new_id, "name": data.name, "type": data.type}
    except pymysql.Error as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        updates = []
        params = []
        if data.name is not None:
            updates.append("username = %s")
            params.append(data.name)
        if data.email is not None:
            updates.append("email = %s")
            params.append(data.email)
        if data.about_me is not None:
            updates.append("about_me = %s")
            params.append(data.about_me)
        if data.type is not None:
            cursor.execute("SELECT id FROM user_types WHERE type = %s", (data.type,))
            type_id = cursor.fetchone()
            if type_id:
                updates.append("type = %s")
                params.append(type_id[0])
        if updates:
            params.append(user_id)
            cursor.execute(f"UPDATE user SET {', '.join(updates)} WHERE id = %s", params)
            db.commit()
        db.close()
        return {"message": "User updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
        db.commit()
        db.close()
        return {"message": "User deleted"}
    except pymysql.Error as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/containers")
async def get_containers():
    if not docker_available:
        import random

        containers = [
            {
                "name": "alfr3d-service-user-1",
                "cpu": round(random.uniform(5, 20), 1),
                "mem": round(random.uniform(30, 60), 1),
                "disk": 20.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-device-1",
                "cpu": round(random.uniform(3, 15), 1),
                "mem": round(random.uniform(25, 45), 1),
                "disk": 15.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-environment-1",
                "cpu": round(random.uniform(8, 25), 1),
                "mem": round(random.uniform(35, 55), 1),
                "disk": 18.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-daemon-1",
                "cpu": round(random.uniform(2, 10), 1),
                "mem": round(random.uniform(20, 35), 1),
                "disk": 12.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-api-1",
                "cpu": round(random.uniform(1, 8), 1),
                "mem": round(random.uniform(15, 30), 1),
                "disk": 8.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-frontend-1",
                "cpu": round(random.uniform(5, 15), 1),
                "mem": round(random.uniform(40, 70), 1),
                "disk": 25.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-mysql-1",
                "cpu": round(random.uniform(10, 30), 1),
                "mem": round(random.uniform(50, 80), 1),
                "disk": 30.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-zookeeper-1",
                "cpu": round(random.uniform(2, 8), 1),
                "mem": round(random.uniform(20, 40), 1),
                "disk": 10.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-kafka-1",
                "cpu": round(random.uniform(15, 35), 1),
                "mem": round(random.uniform(60, 90), 1),
                "disk": 40.0,
                "errors": 0,
            },
        ]
        return containers

    try:
        env = os.environ.copy()
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        containers = []
        output = run_docker_command(["docker", "ps", "-a", "--format", "json"], env)
        container_list = parse_docker_json(output)

        for container in container_list:
            container_name = container.get("Names", "").split(",")[0]
            if not container_name.startswith("alfr3d"):
                continue

            cpu_percent = 0.0
            mem_percent = 0.0

            try:
                stats_output = run_docker_command(
                    [
                        "docker",
                        "stats",
                        "--no-stream",
                        "--format",
                        "{{.CPUPerc}},{{.MemPerc}}",
                        container_name,
                    ],
                    env,
                )
                stats_line = stats_output.strip()
                if stats_line:
                    parts = stats_line.split(",")
                    if len(parts) >= 2:
                        try:
                            cpu_str = parts[0].rstrip("%")
                            mem_str = parts[1].rstrip("%")
                            cpu_percent = float(cpu_str) if cpu_str else 0.0
                            mem_percent = float(mem_str) if mem_str else 0.0
                        except (ValueError, IndexError):
                            pass
            except subprocess.CalledProcessError:
                pass

            disk_percent = 15.0
            try:
                size_output = run_docker_command(
                    [
                        "docker",
                        "ps",
                        "-a",
                        "--size",
                        "--format",
                        "{{.Size}}",
                        "-f",
                        f"name={container_name}",
                    ],
                    env,
                )
                size_str = size_output.strip()
                if size_str:
                    try:
                        size_part = size_str.split(" ")[0]
                        if size_part.endswith("MB"):
                            size_mb = float(size_part[:-2])
                            disk_percent = min(size_mb / 10, 100)
                        elif size_part.endswith("GB"):
                            size_gb = float(size_part[:-2])
                            disk_percent = min(size_gb * 100, 100)
                    except (ValueError, IndexError):
                        pass
            except subprocess.CalledProcessError:
                pass

            status = container.get("Status", "").lower()
            errors = 0 if "up" in status else 1

            containers.append(
                {
                    "name": container_name,
                    "cpu": round(cpu_percent, 1),
                    "mem": round(mem_percent, 1),
                    "disk": round(disk_percent, 1),
                    "errors": errors,
                }
            )

        logger.info(f"Returning {len(containers)} containers")
        await manager.broadcast("containers", containers)
        return containers
    except subprocess.CalledProcessError as e:
        logger.error(f"Error fetching containers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events")
async def get_events():
    return recent_events


@app.get("/api/situational-awareness")
async def get_sa():
    return recent_sa if recent_sa else []


@app.get("/api/devices")
async def get_devices():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, u.username, d.last_online,
                   d.position_x, d.position_y
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            """,
            (ALFR3D_ENV_NAME,),
        )
        devices = []
        for row in cursor.fetchall():
            devices.append(
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
                }
            )
        db.close()
        await manager.broadcast("devices", devices)
        return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users-with-devices")
async def get_users_with_devices():
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute(
            """
            SELECT u.id, u.username as name, u.email, u.about_me, s.state, ut.type,
                   u.last_online, u.created_at
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            JOIN environment e ON u.environment_id = e.id
            WHERE e.name = %s AND u.username NOT IN ('unknown', 'alfr3d')
            ORDER BY u.last_online DESC
            """,
            (ALFR3D_ENV_NAME,),
        )
        users = cursor.fetchall()

        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, ds.state AS device_state,
                   dt.type, d.user_id, d.last_online
            FROM device d
            JOIN states ds ON d.state = ds.id
            JOIN device_types dt ON d.device_type = dt.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            ORDER BY d.last_online DESC
            """,
            (ALFR3D_ENV_NAME,),
        )
        devices = cursor.fetchall()
        db.close()

        devices_by_user = {}
        for d in devices:
            uid = d.pop("user_id")
            if uid not in devices_by_user:
                devices_by_user[uid] = []
            devices_by_user[uid].append(d)

        for user in users:
            user["devices"] = devices_by_user.get(user["id"], [])
            for device in user.get("devices", []):
                device["state"] = device.pop("device_state")
                if device.get("last_online"):
                    device["last_online"] = device["last_online"].isoformat()
            if user.get("last_online"):
                user["last_online"] = user["last_online"].isoformat()
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()

        return users
    except Exception as e:
        logger.error(f"Error fetching users with devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/device-types")
async def get_device_types():
    cache = get_cache()
    cache_key = "api_device_types"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, type FROM device_types")
        types = [{"id": row[0], "type": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, types, ttl=300)
        return types
    except pymysql.Error as e:
        logger.error(f"Error fetching device types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user-types")
async def get_user_types():
    cache = get_cache()
    cache_key = "api_user_types"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, type FROM user_types")
        types = [{"id": row[0], "type": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, types, ttl=300)
        return types
    except pymysql.Error as e:
        logger.error(f"Error fetching user types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/states")
async def get_states():
    cache = get_cache()
    cache_key = "api_states"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, state FROM states")
        states = [{"id": row[0], "state": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, states, ttl=300)
        return states
    except pymysql.Error as e:
        logger.error(f"Error fetching states: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices", status_code=201)
async def create_device(data: DeviceCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM states WHERE state = 'offline'")
        state_row = cursor.fetchone()
        if not state_row:
            raise HTTPException(status_code=500, detail="Offline state not found")
        state_id = state_row[0]
        cursor.execute("SELECT id FROM device_types WHERE type = %s", (data.type,))
        type_row = cursor.fetchone()
        if not type_row:
            raise HTTPException(status_code=400, detail="Invalid device type")
        type_id = type_row[0]
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            raise HTTPException(status_code=500, detail="Environment not found")
        env_id = env_row[0]
        user_id = None
        if data.user:
            cursor.execute("SELECT id FROM user WHERE username = %s", (data.user,))
            user_row = cursor.fetchone()
            if user_row:
                user_id = user_row[0]
        cursor.execute(
            "INSERT INTO device (name, IP, MAC, state, device_type, user_id, environment_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (data.name, data.ip, data.mac, state_id, type_id, user_id, env_id),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return {"id": new_id, "name": data.name, "type": data.type}
    except pymysql.Error as e:
        logger.error(f"Error creating device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        updates = []
        params = []
        if data.name is not None:
            updates.append("name = %s")
            params.append(data.name)
        if data.ip is not None:
            updates.append("IP = %s")
            params.append(data.ip)
        if data.mac is not None:
            updates.append("MAC = %s")
            params.append(data.mac)
        if data.type is not None:
            cursor.execute("SELECT id FROM device_types WHERE type = %s", (data.type,))
            type_row = cursor.fetchone()
            if type_row:
                updates.append("device_type = %s")
                params.append(type_row[0])
        if data.user is not None:
            if data.user:
                cursor.execute("SELECT id FROM user WHERE username = %s", (data.user,))
                user_row = cursor.fetchone()
                if user_row:
                    updates.append("user_id = %s")
                    params.append(user_row[0])
            else:
                updates.append("user_id = NULL")
        if data.position is not None:
            if "x" in data.position and "y" in data.position:
                updates.append("position_x = %s")
                params.append(data.position["x"])
                updates.append("position_y = %s")
                params.append(data.position["y"])
            else:
                updates.append("position_x = NULL")
                updates.append("position_y = NULL")
        if updates:
            params.append(device_id)
            cursor.execute(f"UPDATE device SET {', '.join(updates)} WHERE id = %s", params)
            db.commit()
        db.close()
        return {"message": "Device updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM device WHERE id = %s", (device_id,))
        db.commit()
        db.close()
        return {"message": "Device deleted"}
    except pymysql.Error as e:
        logger.error(f"Error deleting device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/devices")
async def get_user_devices(user_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, d.last_online, u.username
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            WHERE d.user_id = %s
            """,
            (user_id,),
        )
        devices = [
            {
                "id": row[0],
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "last_online": str(row[6]),
                "user": row[7],
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching user devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}/history")
async def get_device_history(device_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT dh.timestamp, dh.name, dh.IP, dh.MAC, s.state,
                   dt.type, u.username, dh.last_online
            FROM device_history dh
            LEFT JOIN states s ON dh.state = s.id
            LEFT JOIN device_types dt ON dh.device_type = dt.id
            LEFT JOIN user u ON dh.user_id = u.id
            WHERE dh.device_id = %s
            ORDER BY dh.timestamp DESC
            """,
            (device_id,),
        )
        history = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "user": row[6],
                "last_online": row[7].isoformat() if row[7] else None,
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return history
    except pymysql.Error as e:
        logger.error(f"Error fetching device history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quips")
async def get_quips():
    try:
        return _get_cached_or_fetch("quips:all", lambda: _fetch_quips())
    except Exception as e:
        logger.error(f"Error fetching quips: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_quips():
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("SELECT id, type, quips FROM quips")
    quips = [{"id": row[0], "type": row[1], "quips": row[2]} for row in cursor.fetchall()]
    db.close()
    return quips


@app.post("/api/quips", status_code=201)
async def create_quip(data: QuipCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("INSERT INTO quips (type, quips) VALUES (%s, %s)", (data.type, data.quips))
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        _invalidate_cache("quips:all")
        return {"id": new_id, "type": data.type, "quips": data.quips}
    except pymysql.Error as e:
        logger.error(f"Error creating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/quips/{quip_id}")
async def update_quip(quip_id: int, data: QuipUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE quips SET type = %s, quips = %s WHERE id = %s",
            (data.type, data.quips, quip_id),
        )
        db.commit()
        db.close()
        _invalidate_cache("quips:all")
        return {"id": quip_id, "type": data.type, "quips": data.quips}
    except Exception as e:
        logger.error(f"Error updating quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/quips/{quip_id}")
async def delete_quip(quip_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM quips WHERE id = %s", (quip_id,))
        db.commit()
        db.close()
        _invalidate_cache("quips:all")
        return {"message": "Quip deleted"}
    except Exception as e:
        logger.error(f"Error deleting quip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weather")
async def get_weather():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            weather_data = {
                "city": row[4],
                "state": row[5],
                "country": row[6],
                "low": row[8],
                "high": row[9],
                "description": row[10],
                "sunrise": row[11].isoformat() if row[11] else None,
                "sunset": row[12].isoformat() if row[12] else None,
                "pressure": row[13],
                "humidity": row[14],
            }
            await manager.broadcast("weather", weather_data)
            return weather_data
        else:
            raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching weather: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/environment")
async def get_environment():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel, timezone FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        logger.debug(f"weather row = {row}")
        if row:
            env_data = {
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
                "description": row[10],
                "sunrise": row[11].isoformat() if row[11] else None,
                "sunset": row[12].isoformat() if row[12] else None,
                "pressure": row[13],
                "humidity": row[14],
                "manual_override": row[15],
                "manual_location_override": row[16],
                "subjective_feel": row[17],
                "timezone": row[18],
            }
            await manager.broadcast("environment", env_data)
            return env_data
        else:
            raise HTTPException(status_code=404, detail="Environment not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/environment")
async def update_environment(data: EnvironmentUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        updates = []
        params = []
        field_mappings = {
            "latitude": "latitude",
            "longitude": "longitude",
            "city": "city",
            "state": "state",
            "country": "country",
            "ip": "IP",
            "temp_min": "low",
            "temp_max": "high",
            "description": "description",
            "pressure": "pressure",
            "humidity": "humidity",
            "subjective_feel": "subjective_feel",
        }
        location_fields = ["latitude", "longitude", "city", "state", "country", "ip"]
        manual_location_override = (
            1 if any(getattr(data, f) is not None for f in location_fields) else 0
        )
        for field, db_field in field_mappings.items():
            value = getattr(data, field, None)
            if value is not None:
                updates.append(f"{db_field} = %s")
                params.append(value)
        updates.append("manual_location_override = %s")
        params.append(manual_location_override)
        if updates:
            params.append(ALFR3D_ENV_NAME)
            sql = f"UPDATE environment SET {', '.join(updates)} WHERE name = %s"
            cursor.execute(sql, params)
            db.commit()
        db.close()
        return {
            "message": "Environment updated",
            "manual_location_override": manual_location_override,
        }
    except pymysql.Error as e:
        logger.error(f"Error updating environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/events")
async def get_calendar_events():
    try:
        db = get_connection()
        cursor = db.cursor()
        today = datetime.now().date()
        cursor.execute(
            "SELECT title, start_time, end_time, address, notes FROM calendar_events "
            "WHERE DATE(start_time) = %s ORDER BY start_time ASC",
            (today,),
        )
        events = [
            {
                "title": row[0],
                "start_time": row[1].isoformat() + "Z" if row[1] else None,
                "end_time": row[2].isoformat() + "Z" if row[2] else None,
                "address": row[3],
                "notes": row[4],
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return events
    except pymysql.Error as e:
        logger.error(f"Error fetching calendar events: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/environment/reset")
async def reset_environment():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, "
            "description, sunrise, sunset, pressure, humidity, manual_override, "
            "manual_location_override, subjective_feel FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        _ = cursor.fetchone()
        db.close()
        return {"message": "Environment reset to auto-detect"}
    except pymysql.Error as e:
        logger.error(f"Error resetting environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/integrations/calendar/sync")
async def trigger_calendar_sync():
    try:
        message = {"type": "calendar", "action": "sync"}
        producer = get_producer()
        producer.send("integrations", message)
        producer.flush()
        logger.info("Calendar sync triggered")
        return {"message": "Calendar sync triggered"}
    except KafkaError as e:
        logger.error(f"Kafka error triggering calendar sync: {e}")
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")
    except Exception as e:
        logger.error(f"Error triggering calendar sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/integrations/gmail/sync")
async def trigger_gmail_sync():
    try:
        message = {"type": "gmail", "action": "sync"}
        producer = get_producer()
        producer.send("integrations", message)
        producer.flush()
        logger.info("Gmail sync triggered")
        return {"message": "Gmail sync triggered"}
    except KafkaError as e:
        logger.error(f"Kafka error triggering gmail sync: {e}")
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")
    except Exception as e:
        logger.error(f"Error triggering gmail sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/integrations/status")
async def get_integrations_status():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT integration_type FROM integrations_tokens WHERE integration_type = 'google'"
        )
        rows = cursor.fetchall()
        db.close()
        connected = bool(rows)
        return {"google": connected}
    except pymysql.Error as e:
        logger.error(f"Error checking integrations status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/api/audio/{filename}", methods=["GET", "HEAD"])
async def get_audio(filename: str):
    logger.info(f"Audio request received for filename: {filename}")

    if not (filename.endswith(".mp3") or filename.endswith(".wav")):
        logger.error(f"Invalid file type for filename: {filename}")
        raise HTTPException(status_code=400, detail="Invalid file type")

    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    audio_path = os.path.join("/tmp/audio", filename)
    if not os.path.exists(audio_path):
        logger.warning(f"Audio file not found: {audio_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")
    logger.info(f"Serving audio file: {audio_path}")

    if filename.endswith(".wav"):
        return FileResponse(audio_path, media_type="audio/wav")
    else:
        return FileResponse(audio_path, media_type="audio/mpeg")


@app.get("/api/iot/ha/status")
async def get_ha_status():
    try:
        from common import ha_utils

        connected, message = ha_utils.test_ha_connection()
        return {"connected": connected, "message": message}
    except Exception as e:
        logger.error(f"Error checking HA status: {str(e)}")
        return {"connected": False, "error": str(e)}


@app.get("/api/iot/ha/devices")
async def get_ha_devices():
    try:
        from common import ha_utils

        devices = ha_utils.get_ha_devices()
        return devices
    except Exception as e:
        logger.error(f"Error fetching HA devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/iot/ha/devices/{entity_id}/control")
async def control_ha_device(entity_id: str, data: HAControl):
    service_map = {
        "turn_on": "turn_on",
        "turn_off": "turn_off",
        "toggle": "toggle",
        "set_brightness": "turn_on",
    }
    service = service_map.get(data.command, data.command)

    try:
        from common import ha_utils

        success, message = ha_utils.ha_control_device(entity_id, service, data.params)
        if success:
            return {"message": message, "entity_id": entity_id, "command": data.command}
        else:
            raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        logger.error(f"Error controlling HA device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/iot/ha/config")
async def save_ha_config(data: HAConfig):
    try:
        from common import ha_utils

        ha_utils.save_ha_config(data.ha_url, data.ha_token)
        return {"message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving HA config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/iot/ha/sync")
async def trigger_ha_sync():
    try:
        producer = get_producer()
        if producer:
            producer.send("device", {"action": "iot_ha_sync"})
            producer.flush()
            logger.info("HA sync triggered")
            return {"message": "Sync triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Kafka")
    except Exception as e:
        logger.error(f"Error triggering HA sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/iot/st/status")
async def get_st_status():
    try:
        from common import st_utils

        connected, message = st_utils.test_st_connection()
        return {"connected": connected, "message": message}
    except Exception as e:
        logger.error(f"Error checking ST status: {str(e)}")
        return {"connected": False, "error": str(e)}


@app.get("/api/iot/st/devices")
async def get_st_devices():
    try:
        from common import st_utils

        devices = st_utils.get_st_devices()
        return devices
    except Exception as e:
        logger.error(f"Error fetching ST devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/iot/st/devices/{device_id}/control")
async def control_st_device(device_id: str, data: STControl):
    try:
        from common import st_utils

        success, message = st_utils.st_control_device(
            device_id, data.capability, data.command, data.args
        )
        if success:
            return {"message": message, "device_id": device_id, "command": data.command}
        else:
            raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        logger.error(f"Error controlling ST device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/iot/st/config")
async def save_st_config(data: STConfig):
    try:
        from common import st_utils

        st_utils.save_st_config(data.st_pat)
        return {"message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving ST config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/iot/st/sync")
async def trigger_st_sync():
    try:
        producer = get_producer()
        if producer:
            producer.send("device", {"action": "iot_st_sync"})
            producer.flush()
            logger.info("ST sync triggered")
            return {"message": "Sync triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Kafka")
    except Exception as e:
        logger.error(f"Error triggering ST sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/iot/status")
async def get_iot_status():
    try:
        from common import ha_utils

        ha_connected, ha_message = ha_utils.test_ha_connection()
        return {
            "ha": {"connected": ha_connected, "message": ha_message},
            "st": {"connected": False, "message": "Not configured"},
        }
    except Exception as e:
        logger.error(f"Error checking IoT status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/iot/devices")
async def get_iot_devices():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM config WHERE name = 'iot_provider'")
        row = cursor.fetchone()
        provider = row[0] if row else "homeassistant"

        cursor.execute(
            """
            SELECT sd.id, sd.name, sd.source, sd.ha_entity_id, sd.st_device_id,
                   sd.device_type, sd.room, sd.capabilities, sd.online, sd.last_state,
                   sd.mac_address, d.id as local_device_id, d.IP, d.position_x, d.position_y
            FROM smarthome_devices sd
            LEFT JOIN device d ON UPPER(d.MAC) = UPPER(sd.mac_address)
            WHERE sd.source = %s
        """,
            (provider,),
        )

        devices = []
        for row in cursor.fetchall():
            devices.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "source": row[2],
                    "ha_entity_id": row[3],
                    "st_device_id": row[4],
                    "device_type": row[5],
                    "room": row[6],
                    "capabilities": orjson.loads(row[7]) if row[7] else [],
                    "online": bool(row[8]),
                    "last_state": orjson.loads(row[9]) if row[9] else {},
                    "mac_address": row[10],
                    "local_device": (
                        {
                            "id": row[11],
                            "IP": row[12],
                            "position_x": row[13],
                            "position_y": row[14],
                        }
                        if row[11]
                        else None
                    ),
                }
            )
        db.close()
        return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching IoT devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/iot/devices/{device_id}/control")
async def control_iot_device(device_id: int, data: IOTDeviceControl):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT source, ha_entity_id FROM smarthome_devices WHERE id = %s",
            (device_id,),
        )
        row = cursor.fetchone()
        db.close()

        if not row:
            raise HTTPException(status_code=404, detail="Device not found")

        source, ha_entity_id = row[0], row[1]

        if source == "homeassistant" and ha_entity_id:
            from common import ha_utils

            service_map = {
                "turn_on": "turn_on",
                "turn_off": "turn_off",
                "toggle": "toggle",
                "set_brightness": "turn_on",
            }
            service = service_map.get(data.command, data.command)
            success, message = ha_utils.ha_control_device(ha_entity_id, service, data.params)
            if success:
                return {
                    "message": message,
                    "device_id": device_id,
                    "command": data.command,
                }
            else:
                raise HTTPException(status_code=500, detail=message)
        else:
            raise HTTPException(status_code=400, detail="Unsupported source or device")
    except Exception as e:
        logger.error(f"Error controlling IoT device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/iot/providers")
async def get_iot_providers():
    return [
        {"id": "homeassistant", "name": "Home Assistant", "status": "configured"},
        {"id": "smartthings", "name": "SmartThings", "status": "not_configured"},
    ]


@app.put("/api/iot/provider")
async def set_iot_provider(data: IoTProvider):
    if data.provider not in ["homeassistant", "smartthings"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("UPDATE config SET value = %s WHERE name = 'iot_provider'", (data.provider,))
        db.commit()
        db.close()
        return {"message": f"Provider set to {data.provider}"}
    except Exception as e:
        logger.error(f"Error setting IoT provider: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/routines")
async def get_routines():
    try:
        cache_key = f"routines:{ALFR3D_ENV_NAME}"
        return _get_cached_or_fetch(cache_key, lambda: _fetch_routines())
    except Exception as e:
        logger.error(f"Error fetching routines: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_routines():
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


@app.post("/api/routines", status_code=201)
async def create_routine(data: RoutineCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            db.close()
            raise HTTPException(status_code=400, detail="Environment not found")
        env_id = env_row[0]

        actions_json = orjson.dumps(data.actions).decode("utf-8")
        recurrence = data.recurrence
        routine_time = normalize_time(data.time)

        cursor.execute(
            "INSERT INTO routines (name, time, enabled, recurrence, actions, environment_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (data.name, routine_time, data.enabled, recurrence, actions_json, env_id),
        )
        db.commit()
        routine_id = cursor.lastrowid
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Created routine: {data.name} (ID: {routine_id})")
        return {"id": routine_id, "message": "Routine created"}
    except Exception as e:
        logger.error(f"Error creating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/routines/{routine_id}")
async def update_routine(routine_id: int, data: RoutineUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        updates = []
        values = []
        if data.name is not None:
            updates.append("name = %s")
            values.append(data.name)
        if data.time is not None:
            updates.append("time = %s")
            values.append(normalize_time(data.time))
        if data.enabled is not None:
            updates.append("enabled = %s")
            values.append(data.enabled)
        if data.recurrence is not None:
            updates.append("recurrence = %s")
            values.append(data.recurrence)
        if data.actions is not None:
            updates.append("actions = %s")
            values.append(orjson.dumps(data.actions).decode("utf-8"))

        if not updates:
            db.close()
            raise HTTPException(status_code=400, detail="No valid fields to update")

        values.append(routine_id)
        query = f"UPDATE routines SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, values)
        db.commit()
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Updated routine ID: {routine_id}")
        return {"message": "Routine updated"}
    except Exception as e:
        logger.error(f"Error updating routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/routines/{routine_id}")
async def delete_routine(routine_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM routines WHERE id = %s", (routine_id,))
        db.commit()
        db.close()
        _invalidate_cache(f"routines:{ALFR3D_ENV_NAME}")
        logger.info(f"Deleted routine ID: {routine_id}")
        return {"message": "Routine deleted"}
    except Exception as e:
        logger.error(f"Error deleting routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/routines/{routine_id}/run")
async def run_routine(routine_id: int):
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT r.*, e.name as env_name FROM routines r "
            "JOIN environment e ON r.environment_id = e.id WHERE r.id = %s",
            (routine_id,),
        )
        routine = cursor.fetchone()

        if not routine:
            db.close()
            raise HTTPException(status_code=404, detail="Routine not found")

        actions = orjson.loads(routine["actions"]) if routine.get("actions") else []

        cursor.execute("UPDATE routines SET last_run = NOW() WHERE id = %s", (routine_id,))
        db.commit()
        db.close()

        kafka_producer = get_producer()
        if not kafka_producer:
            raise HTTPException(status_code=500, detail="Kafka not available")

        for action in actions:
            action_type = action.get("type")
            action_params = action.get("params", {})

            if action_type == "speak":
                message = {"text": action_params.get("text", ""), "engine": "Coqui"}
                kafka_producer.send("speak", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent speak action")
            elif action_type == "device":
                device_id = action_params.get("device_id")
                device_action = action_params.get("action", "on")
                message = {"device_id": device_id, "action": device_action}
                kafka_producer.send("device", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent device action")
            elif action_type == "email":
                message = {
                    "type": "email",
                    "to": action_params.get("to", ""),
                    "subject": action_params.get("subject", ""),
                    "body": action_params.get("body", ""),
                }
                kafka_producer.send("user", message)
                kafka_producer.flush()
                logger.info(f"Routine {routine_id}: Sent email action")

        return {"message": "Routine executed", "actions_run": len(actions)}
    except Exception as e:
        logger.error(f"Error running routine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/api/personality")
async def get_personality():
    try:
        return _get_cached_or_fetch("personality:current", _fetch_personality)
    except pymysql.Error as e:
        logger.error(f"Error fetching personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_personality():
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
    raise HTTPException(status_code=404, detail="Personality not found")


@app.put("/api/personality")
async def update_personality(data: PersonalityUpdate):
    try:
        env_id = get_environment_id()
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE personality SET "
            "sarcasm = %s, formality = %s, warmth = %s, patience = %s, "
            "linguistic_style = %s, forbidden_words = %s, verbal_tics = %s, "
            "name = %s WHERE type = 'current' AND environment_id = %s",
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
            ),
        )
        db.commit()
        db.close()
        _invalidate_cache("personality:current")
        return {"message": "Personality updated"}
    except Exception as e:
        logger.error(f"Error updating personality: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/personality/presets")
async def get_personality_presets():
    try:
        return _get_cached_or_fetch("personality:presets", _fetch_personality_presets)
    except Exception as e:
        logger.error(f"Error fetching presets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_personality_presets():
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


@app.post("/api/personality/apply-preset")
async def apply_personality_preset(data: PresetApply):
    try:
        env_id = get_environment_id()
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT * FROM personality WHERE type = 'preset' AND name = %s",
            (data.preset,),
        )
        preset = cursor.fetchone()
        if not preset:
            db.close()
            raise HTTPException(status_code=404, detail="Preset not found")

        cursor.execute(
            "UPDATE personality SET "
            "sarcasm = %s, formality = %s, warmth = %s, patience = %s, "
            "linguistic_style = %s, forbidden_words = %s, verbal_tics = %s, "
            "name = %s WHERE type = 'current' AND environment_id = %s",
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
            ),
        )
        db.commit()
        db.close()
        _invalidate_cache("personality:current")
        return {"message": f"Applied preset: {data.preset}"}
    except Exception as e:
        logger.error(f"Error applying preset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/personality/context")
async def get_personality_context():
    try:
        env_id = get_environment_id()
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM context WHERE environment_id = %s LIMIT 1", (env_id,))
        row = cursor.fetchone()
        db.close()
        if row:
            return {
                "repeat_count": row["repeat_count"],
                "hour": row["hour"],
                "weather": row["weather"] or "clear",
                "mood": row["mood"],
                "last_error_count": row["last_error_count"],
                "llm_calls_today": row["llm_calls_today"],
            }
        raise HTTPException(status_code=404, detail="Context not found")
    except pymysql.Error as e:
        logger.error(f"Error fetching context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/personality/context")
async def update_personality_context(data: ContextUpdate):
    try:
        env_id = get_environment_id()
        db = get_connection()
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
        db.close()
        return {"message": "Context updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/personality/llm-config")
async def get_llm_config():
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT name, value FROM config WHERE name IN ('llm_api_key', 'llm_usage_limit')"
        )
        rows = cursor.fetchall()
        db.close()
        config = {row[0]: row[1] for row in rows}
        return {
            "api_key": config.get("llm_api_key", ""),
            "usage_limit": int(config.get("llm_usage_limit", 10)),
        }
    except pymysql.Error as e:
        logger.error(f"Error fetching LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/personality/llm-config")
async def update_llm_config(data: LLMConfigUpdate):
    try:
        db = get_connection()
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
        db.commit()
        db.close()
        return {"message": "LLM config updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5001)
