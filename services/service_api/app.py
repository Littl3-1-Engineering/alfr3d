"""REST API service for ALFR3D using FastAPI."""

import asyncio
import os
import sys
import logging
import queue
import threading
from contextlib import asynccontextmanager

import orjson
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from kafka import KafkaConsumer
from kafka.errors import KafkaError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from tree_of_alfr3d import project_tree_router, start_file_watcher_task, set_manager  # noqa: E402

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
