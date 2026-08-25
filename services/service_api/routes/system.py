"""System administration routes: network, database, config editor, service control."""

import asyncio
import logging
import os
import re
import socket
import subprocess
from fastapi import APIRouter, Depends, HTTPException

from dependencies import (
    db_connection,
    docker_available,
    run_docker_command,
    MYSQL_DATABASE,
    MYSQL_USER,
    MYSQL_PSWD,
    MYSQL_DB,
)
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["system"])

# Docker container names accept a wider charset than we want to hand to the docker CLI;
# restrict to the alfr3d-managed containers so a caller can't pass docker flags or target
# unrelated containers on the host.
SERVICE_NAME_RE = re.compile(r"^alfr3d[a-zA-Z0-9_.-]*$")


def _run(command: list, env=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, env=env)
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Error running {' '.join(command)}: {e}")
        return None


def _get_ip():
    for cmd in (
        ["hostname", "-I"],
        ["sh", "-c", "hostname -I"],
    ):
        out = _run(cmd)
        if out:
            parts = out.split()
            return parts[0]
    return socket.gethostbyname(socket.gethostname())


@router.get("/system/network")
async def get_network():
    try:
        hostname = socket.gethostname()
        ip = _get_ip()
        dns = _run(
            ["sh", "-c", "cat /etc/resolv.conf | grep nameserver | head -1 | awk '{print $2}'"]
        )
        gateway = _run(["sh", "-c", "ip route | grep default | awk '{print $3}' | head -1"])
        return {
            "hostname": hostname,
            "ip": ip,
            "dns": dns or "",
            "gateway": gateway or "",
        }
    except Exception as e:
        logger.error(f"Error fetching network info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _table_counts():
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT table_name, table_rows FROM information_schema.tables "
            "WHERE table_schema = DATABASE() ORDER BY table_name"
        )
        rows = cursor.fetchall()
    return [{"name": row[0], "rows": row[1]} for row in rows]


@router.get("/system/database")
async def get_database():
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
        tables = await asyncio.get_event_loop().run_in_executor(None, _table_counts)
        return {"connected": True, "version": version, "tables": tables}
    except Exception as e:
        logger.error(f"Error fetching database info: {str(e)}")
        return {
            "connected": False,
            "version": "",
            "tables": [],
            "error": "Failed to fetch database info",
        }


@router.post("/system/database/backup")
async def backup_database(_perm=Depends(require_permission("system", "backup"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("SHOW DATABASES")
            databases = [
                row[0]
                for row in cursor.fetchall()
                if row[0] not in ("information_schema", "performance_schema", "mysql", "sys")
            ]

        if not databases:
            databases = [MYSQL_DB]
        for db_name in databases:
            result = subprocess.run(
                [
                    "mysqldump",
                    f"--host={MYSQL_DATABASE}",
                    f"--user={MYSQL_USER}",
                    f"--password={MYSQL_PSWD}",
                    db_name,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"mysqldump failed: {result.stderr}")
                raise HTTPException(status_code=500, detail="mysqldump failed")
            filename = f"/backups/{db_name}.sql"
            os.makedirs("/backups", exist_ok=True)
            with open(filename, "w") as f:
                f.write(result.stdout)
        return {"message": "Database backup completed", "databases": databases}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error backing up database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


CONFIG_PATH = "/etc/alfr3d/config.json"


def _read_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return f.read()
    return "{}"


@router.get("/system/config")
async def get_config():
    try:
        return {"path": CONFIG_PATH, "content": _read_config()}
    except Exception as e:
        logger.error(f"Error reading config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/system/config")
async def save_config(data: dict, _perm=Depends(require_permission("system", "update_config"))):
    try:
        content = data.get("content")
        if content is None:
            raise HTTPException(status_code=400, detail="content is required")
        import orjson

        parsed = orjson.loads(content)
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            f.write(orjson.dumps(parsed, option=orjson.OPT_INDENT_2).decode())
        return {"message": "Config saved", "path": CONFIG_PATH}
    except orjson.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/services")
async def get_services():
    try:
        if not docker_available:
            return [
                {"name": "api", "status": "running"},
                {"name": "daemon", "status": "running"},
                {"name": "frontend", "status": "running"},
                {"name": "environment", "status": "running"},
            ]
        env = os.environ.copy()
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        output = run_docker_command(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"], env
        )
        services = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0].startswith("alfr3d"):
                continue
            status = "running" if "Up" in parts[1] else "stopped"
            services.append({"name": parts[0], "status": status})
        return services
    except Exception as e:
        logger.error(f"Error fetching services: {str(e)}")
        return []


@router.post("/system/services/{service_name}/restart")
async def restart_service(
    service_name: str, _perm=Depends(require_permission("system", "restart_service"))
):
    if not SERVICE_NAME_RE.match(service_name):
        raise HTTPException(status_code=400, detail="Invalid service name")
    try:
        if not docker_available:
            return {"message": f"Restart requested for {service_name} (docker unavailable)"}
        env = os.environ.copy()
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        output = run_docker_command(["docker", "restart", service_name], env)
        return {"message": f"Restart triggered: {service_name}", "output": output}
    except Exception as e:
        logger.error(f"Error restarting service {service_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
