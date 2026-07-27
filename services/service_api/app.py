"""REST API service for ALFR3D using FastAPI."""

import asyncio
import os
import sys
import logging
import subprocess
from contextlib import asynccontextmanager

import orjson
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from kafka import KafkaConsumer
from kafka.errors import KafkaError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from tree_of_alfr3d import project_tree_router, start_file_watcher_task, set_manager

from dependencies import (
    manager, recent_events, recent_sa, KAFKA_URL,
)
from routes.users import router as users_router
from routes.devices import router as devices_router
from routes.quips import router as quips_router
from routes.environment import router as environment_router
from routes.integrations import router as integrations_router
from routes.audio import router as audio_router
from routes.events import router as events_router
from routes.containers import router as containers_router, collect_container_metrics
from routes.routines import router as routines_router
from routes.personality import router as personality_router
from routes.iot import router as iot_router

CURRENT_PATH = os.path.dirname(__file__)

logger = logging.getLogger("ApiLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_manager(manager)
    asyncio.create_task(consume_events())
    asyncio.create_task(consume_sa())
    asyncio.create_task(collect_container_metrics())
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
