"""Container monitoring routes and background task."""

import asyncio
import logging
from fastapi import APIRouter, HTTPException

from dependencies import docker_available, manager, run_docker_command, parse_docker_json

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["containers"])


def fetch_container_metrics() -> list:
    if not docker_available:
        import random

        return [
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

    import os
    import subprocess

    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    containers = []
    output = run_docker_command(["docker", "ps", "-a", "--format", "{{json .}}"], env)
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
                        cpu_percent = float(parts[0].rstrip("%")) if parts[0].rstrip("%") else 0.0
                        mem_percent = float(parts[1].rstrip("%")) if parts[1].rstrip("%") else 0.0
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
                        disk_percent = min(float(size_part[:-2]) / 10, 100)
                    elif size_part.endswith("GB"):
                        disk_percent = min(float(size_part[:-2]) * 100, 100)
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
