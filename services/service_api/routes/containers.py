"""Container monitoring routes and background task."""

import asyncio
import logging
import os
import random
import subprocess
from fastapi import APIRouter, HTTPException

from dependencies import is_docker_available, manager, run_docker_command, parse_docker_json

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["containers"])


# "docker stats" reports CPU as a percentage of a single core, so a container using two
# cores reads 200%. Normalize against the host's core count to keep the value in 0-100.
_ncpu_cache = {"value": None}


def _host_ncpu(env) -> int:
    if _ncpu_cache["value"] is None:
        ncpu = 0
        try:
            output = run_docker_command(["docker", "info", "--format", "{{.NCPU}}"], env)
            ncpu = int(output.strip())
        except (subprocess.SubprocessError, ValueError) as e:
            logger.warning(f"Could not read host CPU count from docker ({e}), using os.cpu_count()")
        _ncpu_cache["value"] = ncpu if ncpu > 0 else (os.cpu_count() or 1)
    return _ncpu_cache["value"]


def _mock_container_metrics() -> list:
    def sample(name, cpu_range, mem_range):
        return {
            "name": name,
            "cpu": round(random.uniform(*cpu_range), 1),
            "mem": round(random.uniform(*mem_range), 1),
            "state": "running",
            "health": "healthy",
            "restarts": 0,
        }

    return [
        sample("alfr3d-service-user-1", (5, 20), (30, 60)),
        sample("alfr3d-service-device-1", (3, 15), (25, 45)),
        sample("alfr3d-service-environment-1", (8, 25), (35, 55)),
        sample("alfr3d-service-daemon-1", (2, 10), (20, 35)),
        sample("alfr3d-service-api-1", (1, 8), (15, 30)),
        sample("alfr3d-service-frontend-1", (5, 15), (40, 70)),
        sample("alfr3d-mysql-1", (10, 30), (50, 80)),
        sample("alfr3d-zookeeper-1", (2, 8), (20, 40)),
        sample("alfr3d-kafka-1", (15, 35), (60, 90)),
    ]


def _fetch_stats(env) -> dict:
    """CPU/memory for every running container, in a single docker call.

    Querying one container at a time costs a full ~2s docker round trip each, which is
    what used to stretch the 10s collection interval out to 30s.
    """
    stats = {}
    try:
        output = run_docker_command(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}},{{.CPUPerc}},{{.MemPerc}}"],
            env,
        )
    except subprocess.SubprocessError as e:
        logger.warning(f"Could not read container stats: {e}")
        return stats

    ncpu = _host_ncpu(env)
    for line in output.strip().split("\n"):
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            stats[parts[0]] = (float(parts[1].rstrip("%")) / ncpu, float(parts[2].rstrip("%")))
        except ValueError:
            continue
    return stats


def _fetch_states(names: list, env) -> dict:
    """Lifecycle state, healthcheck verdict and restart count, in a single docker call."""
    states = {}
    fmt = (
        "{{.Name}},{{.State.Status}},"
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}},"
        "{{.RestartCount}}"
    )
    try:
        output = run_docker_command(["docker", "inspect", "--format", fmt] + names, env)
    except subprocess.SubprocessError as e:
        logger.warning(f"Could not inspect containers: {e}")
        return states

    for line in output.strip().split("\n"):
        parts = line.strip().split(",")
        if len(parts) < 4:
            continue
        try:
            restarts = int(parts[3])
        except ValueError:
            restarts = 0
        states[parts[0].lstrip("/")] = (parts[1], parts[2], restarts)
    return states


def fetch_container_metrics() -> list:
    """Per-container utilization plus Docker's own health verdict.

    CPU/memory are reported as utilization only. Health is whatever Docker says it is --
    deriving it from resource usage would call a busy container a dying one, which is how
    a Kafka healthcheck burst used to render as 0%/CRITICAL.
    """
    if not is_docker_available():
        return _mock_container_metrics()

    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"

    output = run_docker_command(["docker", "ps", "-a", "--format", "{{json .}}"], env)
    # Containers recreated out of band pick up a hash prefix (2a2c09387c6c_alfr3d-mysql-1),
    # so match "alfr3d" anywhere in the name rather than only at the start.
    names = [
        name
        for name in (c.get("Names", "").split(",")[0] for c in parse_docker_json(output))
        if "alfr3d" in name
    ]
    if not names:
        return []

    stats = _fetch_stats(env)
    states = _fetch_states(names, env)

    containers = []
    for name in names:
        cpu_percent, mem_percent = stats.get(name, (0.0, 0.0))
        state, health, restarts = states.get(name, ("unknown", "none", 0))
        containers.append(
            {
                "name": name,
                "cpu": round(cpu_percent, 1),
                "mem": round(mem_percent, 1),
                "state": state,
                "health": health,
                "restarts": restarts,
            }
        )

    return containers


async def collect_container_metrics():
    while True:
        try:
            containers = await asyncio.get_event_loop().run_in_executor(
                None, fetch_container_metrics
            )
            logger.info(f"Broadcasting {len(containers)} containers via WebSocket")
            await manager.broadcast("containers", containers)
        except Exception as e:
            logger.error(f"Error collecting container metrics: {str(e)}")
        await asyncio.sleep(10)


@router.get("/containers")
async def get_containers():
    try:
        containers = await asyncio.get_event_loop().run_in_executor(None, fetch_container_metrics)
        logger.info(f"Returning {len(containers)} containers")
        return containers
    except Exception as e:
        logger.error(f"Error fetching containers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
