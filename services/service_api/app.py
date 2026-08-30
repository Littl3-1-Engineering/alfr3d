"""REST API service for ALFR3D using FastAPI."""

import asyncio
import os
import sys
import logging
import queue
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import orjson
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from kafka import KafkaConsumer
from kafka.errors import KafkaError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from tree_of_alfr3d import project_tree_router, start_file_watcher_task, set_manager  # noqa: E402
from common import db_connection  # noqa: E402

from dependencies import (  # noqa: E402
    manager,
    recent_events,
    recent_sa,
    KAFKA_URL,
    _fetch_users,
    _fetch_devices,
)
from routes.users import router as users_router  # noqa: E402
from routes.devices import router as devices_router  # noqa: E402
from routes.quips import router as quips_router  # noqa: E402
from routes.environment import router as environment_router, broadcast_calendar_events  # noqa: E402
from routes.integrations import router as integrations_router  # noqa: E402
from routes.audio import router as audio_router  # noqa: E402
from routes.events import router as events_router  # noqa: E402
from routes.containers import router as containers_router, collect_container_metrics  # noqa: E402
from routes.routines import router as routines_router  # noqa: E402
from routes.personality import router as personality_router  # noqa: E402
from routes.iot import router as iot_router, broadcast_iot_devices  # noqa: E402
from routes.stream import router as stream_router  # noqa: E402
from routes.health import router as health_router  # noqa: E402
from routes.system import router as system_router  # noqa: E402
from routes.music import router as music_router  # noqa: E402
from routes.context import router as context_router  # noqa: E402
from auth.routes import router as auth_router  # noqa: E402

CURRENT_PATH = os.path.dirname(__file__)

logger = logging.getLogger("ApiLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


# event-stream messages carry no explicit producer identity today (see
# SA-11 Phase 0 investigation) -- these prefixes match every current
# send_event()/inline-publish call site's `id` format. A future Phase 2
# producer migration can just set an explicit "service" key instead of
# growing this list; _infer_source_service() prefers that key when present.
_SOURCE_SERVICE_ID_PREFIXES = (
    ("device_", "device"),
    ("environment_", "environment"),
    ("weather_", "environment"),
    ("user_", "user"),
    ("speak_", "speak"),
    ("personality_", "speak"),
    ("song_start_", "daemon"),
    ("song_end_", "daemon"),
    ("now_playing_", "daemon"),
    ("gathering_detected_", "daemon"),
    ("schedule_setup_", "daemon"),
    ("setup_complete_", "daemon"),
    ("calendar_event_created_", "daemon"),
    ("calendar_event_removed_", "daemon"),
)


def _infer_source_service(event: dict) -> str:
    """Best-effort source-service label for a durable household_events row."""
    service = event.get("service")
    if service:
        return service
    event_id = event.get("id") or ""
    for prefix, service in _SOURCE_SERVICE_ID_PREFIXES:
        if event_id.startswith(prefix):
            return service
    return "unknown"


def _parse_event_time(raw) -> datetime:
    """Parse an event-stream `time` string, tolerating the malformed
    ``<isoformat-with-offset>Z`` strings some producers emit (offset and
    "Z" both present). Falls back to the current time rather than dropping
    the event on an unparseable timestamp."""
    if not raw:
        return datetime.now(timezone.utc)
    text = raw[:-1] if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        logger.warning(f"Unparseable event time {raw!r}; using current time")
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _persist_household_events(events: list) -> None:
    """Durable second destination for event-stream messages (SA-11 Phase 1).

    The in-memory recent_events buffer stays the source for the live
    dashboard feed; this only adds a parallel INSERT so a DB hiccup here
    must never affect that buffer or its broadcast.
    """
    if not events:
        return

    def _insert():
        rows = [
            (
                event.get("type", "unknown"),
                event.get("message"),
                event.get("subject_type"),
                event.get("subject_id"),
                event.get("verb"),
                _parse_event_time(event.get("time")),
                _infer_source_service(event),
            )
            for event in events
        ]
        with db_connection() as db:
            cursor = db.cursor()
            cursor.executemany(
                "INSERT INTO household_events "
                "(event_type, message, subject_type, subject_id, verb, occurred_at, "
                "source_service) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
            db.commit()

    try:
        await asyncio.to_thread(_insert)
    except Exception as e:
        logger.error(f"Failed to persist household events: {e}")


def _kafka_pump(topic: str, out_q: "queue.Queue", stop_event: threading.Event) -> None:
    """Run a blocking Kafka consumer on a dedicated thread, pushing messages to a queue."""
    logger.info(f"Kafka pump started for {topic}: {KAFKA_URL}")
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=KAFKA_URL,
            auto_offset_reset="latest",
            consumer_timeout_ms=1000,
        )
        logger.info(f"Connected to Kafka topic {topic}")
        while not stop_event.is_set():
            for message in consumer:
                if stop_event.is_set():
                    break
                try:
                    out_q.put_nowait(message.value)
                except queue.Full:
                    logger.warning(f"Kafka queue full for {topic}, dropping message")
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for {topic}: {str(e)}")


async def consume_events():
    q: "asyncio.Queue" = asyncio.Queue(maxsize=1000)
    stop_event = threading.Event()
    t = threading.Thread(target=_kafka_pump, args=("event-stream", q, stop_event), daemon=True)
    t.start()
    try:
        while True:
            try:
                value = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                data = orjson.loads(value)
                events_to_send = data if isinstance(data, list) else [data]
                if isinstance(data, list):
                    recent_events.extend(data)
                else:
                    recent_events.append(data)
                recent_events[:] = recent_events[-20:]
                logger.info(f"Received events: {data}")
                await manager.broadcast("events", recent_events)
                await _persist_household_events(events_to_send)
                for event in events_to_send:
                    try:
                        headers = {"Content-Type": "application/json"}
                        url = "https://ntfy.sh/alfr3d-event-stream"
                        await asyncio.to_thread(
                            requests.post,
                            url,
                            json=event,
                            headers=headers,
                            timeout=3,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send event to nfty.sh: {e}")
            except orjson.JSONDecodeError as e:
                logger.error(f"Error processing event message: {str(e)}")
            except Exception as e:
                logger.error(f"Error handling event: {str(e)}")
    finally:
        stop_event.set()


async def consume_sa():
    q: "asyncio.Queue" = asyncio.Queue(maxsize=1000)
    stop_event = threading.Event()
    t = threading.Thread(
        target=_kafka_pump,
        args=("situational-awareness", q, stop_event),
        daemon=True,
    )
    t.start()
    try:
        while True:
            try:
                value = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                data = orjson.loads(value)
                recent_sa.clear()
                if isinstance(data, list):
                    recent_sa.extend(data)
                else:
                    recent_sa.append(data)
                logger.info(f"Received SA: {data}")
                await manager.broadcast("situational_awareness", recent_sa)
            except orjson.JSONDecodeError as e:
                logger.error(f"Error processing SA message: {str(e)}")
            except Exception as e:
                logger.error(f"Error handling SA message: {str(e)}")
    finally:
        stop_event.set()


async def broadcast_users():
    while True:
        try:
            users = await asyncio.get_event_loop().run_in_executor(None, _fetch_users)
            await manager.broadcast("users", users)
        except Exception as e:
            logger.error(f"Error broadcasting users: {str(e)}")
        await asyncio.sleep(5)


async def broadcast_devices():
    while True:
        try:
            devices = await asyncio.get_event_loop().run_in_executor(None, _fetch_devices)
            await manager.broadcast("devices", devices)
        except Exception as e:
            logger.error(f"Error broadcasting devices: {str(e)}")
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    asyncio.create_task(consume_events())
    asyncio.create_task(consume_sa())
    asyncio.create_task(collect_container_metrics())
    asyncio.create_task(broadcast_users())
    asyncio.create_task(broadcast_devices())
    asyncio.create_task(broadcast_iot_devices())
    asyncio.create_task(broadcast_calendar_events())
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


app.include_router(project_tree_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(quips_router)
app.include_router(environment_router)
app.include_router(integrations_router)
app.include_router(audio_router)
app.include_router(events_router)
app.include_router(containers_router)
app.include_router(routines_router)
app.include_router(personality_router)
app.include_router(iot_router)
app.include_router(stream_router)
app.include_router(health_router)
app.include_router(system_router)
app.include_router(music_router)
app.include_router(context_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5001)
