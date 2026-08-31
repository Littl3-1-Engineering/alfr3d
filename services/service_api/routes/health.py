"""Health and uptime routes."""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from dependencies import docker_available, run_docker_command

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["health"])

# Last-resort fallback for when neither ALFR3D_VERSION nor the VERSION file is readable --
# deliberately not a real version number, so a broken lookup is visibly "unknown" rather than
# silently showing a stale hardcoded version that rots with every release (as "0.1.8" did).
UNKNOWN_VERSION = "unknown"
_UPTIME_RE = re.compile(
    r"Up (?:(?P<days>\d+) days?)?\s*(?:(?P<hours>\d+) hours?)?\s*"
    r"(?:(?P<minutes>\d+) minutes?)?\s*(?:(?P<seconds>\d+) seconds?)?"
)


def _read_version() -> str:
    env_version = os.environ.get("ALFR3D_VERSION")
    if env_version:
        return env_version

    # services/VERSION is the single source of truth for the version number. The Docker image
    # flattens it to /app/VERSION (2 dirs up from this file), which is also where a local,
    # non-Docker run finds it if service_api's own VERSION file exists; a plain local checkout
    # has it one directory higher, at services/VERSION (3 dirs up). Try both.
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = (
        os.path.join(service_dir, "VERSION"),
        os.path.join(os.path.dirname(service_dir), "VERSION"),
    )
    for version_file in candidates:
        try:
            with open(version_file, "r") as f:
                version = f.read().strip()
                if version:
                    return version
        except (IOError, OSError):
            continue
    return UNKNOWN_VERSION


def _parse_uptime(status: str) -> float | None:
    if "Up" not in status:
        return None
    if "About a minute" in status:
        return 60.0
    if "Less than a second" in status:
        return 1.0
    m = _UPTIME_RE.search(status)
    if not m:
        return None
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _fetch_service_uptimes() -> list:
    if not docker_available:
        return [
            {"name": "alfr3d-service-api-1", "uptime_seconds": 259200},
            {"name": "alfr3d-service-frontend-1", "uptime_seconds": 259200},
            {"name": "alfr3d-service-daemon-1", "uptime_seconds": 172800},
        ]

    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    output = run_docker_command(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"], env)
    services = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[0]
        if not name.startswith("alfr3d"):
            continue
        services.append({"name": name, "uptime_seconds": _parse_uptime(parts[1])})
    return services


@router.get("/health")
async def get_health():
    try:
        services = await asyncio.get_event_loop().run_in_executor(None, _fetch_service_uptimes)
    except Exception as e:
        logger.error(f"Error fetching health: {str(e)}")
        services = []

    uptimes = [s["uptime_seconds"] for s in services if s["uptime_seconds"] is not None]
    system_uptime = min(uptimes) if uptimes else None
    now = datetime.now(timezone.utc)
    started_at = (
        (now - timedelta(seconds=system_uptime)).isoformat() if system_uptime else now.isoformat()
    )

    return {
        "status": "ok",
        "version": _read_version(),
        "uptime_seconds": system_uptime,
        "started_at": started_at,
        "services": services,
    }
