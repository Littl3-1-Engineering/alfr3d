"""Events and situational awareness routes."""

import asyncio
from typing import Optional

import orjson
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from dependencies import recent_events, recent_sa, subscribe_events, unsubscribe_events

router = APIRouter(prefix="/api", tags=["events"])

# Comment line sent whenever no event arrived for this long. Keeps the connection from looking
# idle to nginx (proxy_read_timeout is 120s) and to NAT/cellular middleboxes, and lets a client
# tell "quiet" from "dead" with a read timeout a few multiples of this.
SSE_HEARTBEAT_SECONDS = 20


@router.get("/events")
async def get_events():
    return recent_events


def _sse_message(event):
    """One SSE message for an event dict: `id:` carries the event's own id when it has one."""
    lines = []
    event_id = event.get("id")
    if event_id:
        lines.append(f"id: {str(event_id).replace(chr(10), ' ')}")
    lines.append(f"data: {orjson.dumps(event).decode('utf-8')}")
    return "\n".join(lines) + "\n\n"


@router.get("/events/stream")
async def stream_events(types: Optional[str] = None):
    """Server-sent events: every event-stream message received from now on, pushed as it
    arrives (no replay of `recent_events` -- a reconnecting client must not re-hear old
    speech). `?types=audio,...` limits the stream to those event `type`s. Read-only, like
    GET /api/events. Used by the Deck's phone-speech relay so a locked phone can hold one idle
    connection instead of polling every 20s.
    """
    wanted = {t.strip() for t in types.split(",") if t.strip()} if types else None
    queue = subscribe_events()

    async def generate():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if not isinstance(event, dict):
                    continue
                if wanted is not None and event.get("type") not in wanted:
                    continue
                yield _sse_message(event)
        finally:
            unsubscribe_events(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        # X-Accel-Buffering: tell nginx not to buffer this response or the client sees nothing.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/situational-awareness")
async def get_sa():
    return recent_sa if recent_sa else []
