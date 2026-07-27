"""Events and situational awareness routes."""

from fastapi import APIRouter

from dependencies import recent_events, recent_sa

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def get_events():
    return recent_events


@router.get("/situational-awareness")
async def get_sa():
    return recent_sa if recent_sa else []
