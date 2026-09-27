"""System administration routes: network, database, config editor, service control."""

import asyncio
import logging
import os
import re
import socket
import subprocess
from datetime import datetime, timezone

import orjson
import requests
from fastapi import APIRouter, Depends, HTTPException

from dependencies import (
    _get_cached_or_fetch,
    db_connection,
    is_docker_available,
    manager,
    read_version,
    run_docker_command,
    MYSQL_DATABASE,
    MYSQL_USER,
    MYSQL_PSWD,
    MYSQL_DB,
)
from auth import password_utils
from auth.dependencies import CurrentUser, require_permission
from models import UpdateStartRequest

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


GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/Littl3-1-Engineering/alfr3d/releases/latest"
)
_UPDATE_CHECK_CACHE_KEY = "api:system:update_check"
_UPDATE_CHECK_TTL = 6 * 60 * 60  # releases don't ship more than a few times a week


def _fetch_latest_release():
    current_version = read_version()
    try:
        resp = requests.get(
            GITHUB_LATEST_RELEASE_URL,
            headers={
                "User-Agent": "alfr3d-service-api",
                "Accept": "application/vnd.github+json",
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "")
        return {
            "current_version": current_version,
            "latest_tag": latest_tag,
            "latest_title": data.get("name") or latest_tag,
            "release_notes_url": data.get("html_url", ""),
            "release_body": data.get("body", ""),
            "published_at": data.get("published_at", ""),
            # Releases here only ever move forward, so "not equal to current" is enough --
            # no real semver comparison needed.
            "update_available": bool(latest_tag) and latest_tag.lstrip("v") != current_version,
        }
    except Exception as e:
        logger.warning(f"Error checking for new release: {str(e)}")
        return {
            "current_version": current_version,
            "latest_tag": "",
            "latest_title": "",
            "release_notes_url": "",
            "release_body": "",
            "published_at": "",
            "update_available": False,
        }


@router.get("/system/update-check")
async def get_update_check():
    return _get_cached_or_fetch(_UPDATE_CHECK_CACHE_KEY, _fetch_latest_release, _UPDATE_CHECK_TTL)


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


BACKUP_DIR = "/backups"


def _perform_database_backup() -> dict:
    """Runs mysqldump for every user database, writing timestamped .sql files to BACKUP_DIR.
    Timestamped rather than a fixed `{db_name}.sql` -- the old fixed name meant a routine manual
    backup could silently clobber a safety backup an in-progress update just took, since both
    wrote to the same path. Raises HTTPException(500) on any failure (fail closed -- a caller
    that needs a backup before proceeding, like the update flow, must never treat a failed backup
    as a success)."""
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

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    files = []
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
            logger.error(f"mysqldump failed for {db_name}: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"mysqldump failed for {db_name}")
        filename = f"{BACKUP_DIR}/{db_name}_{timestamp}.sql"
        with open(filename, "w") as f:
            f.write(result.stdout)
        files.append(filename)
    return {"databases": databases, "timestamp": timestamp, "files": files}


@router.post("/system/database/backup")
async def backup_database(_perm=Depends(require_permission("system", "backup"))):
    try:
        result = _perform_database_backup()
        return {"message": "Database backup completed", "databases": result["databases"]}
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
        if not is_docker_available():
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
        if not is_docker_available():
            return {"message": f"Restart requested for {service_name} (docker unavailable)"}
        env = os.environ.copy()
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        output = run_docker_command(["docker", "restart", service_name], env)
        return {"message": f"Restart triggered: {service_name}", "output": output}
    except Exception as e:
        logger.error(f"Error restarting service {service_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Self-service update execution (todo/todo_selfservice_release_update.md). service-api never
# runs `git`/`docker compose build` itself -- it only spawns a one-shot, never-`up -d`'d
# `service-updater` container via its existing docker.sock (profiles: ["tools"] in
# docker-compose.yml) and reports back whatever that container writes to the shared status file.
STATUS_FILE_PATH = "/status/update_status.json"


def _project_name() -> str:
    return os.environ.get("COMPOSE_PROJECT_NAME", "alfr3d")


def _read_update_status():
    try:
        with open(STATUS_FILE_PATH, "rb") as f:
            return orjson.loads(f.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        return None


@router.post("/system/update/start")
async def start_update(
    data: UpdateStartRequest,
    user: CurrentUser = Depends(require_permission("system", "update")),
):
    # Re-proving the caller's own password is the second checkpoint alongside the frontend's
    # release-notes confirm dialog -- the same primitive /api/auth/change-password already uses,
    # not new password infrastructure. Checked before anything else runs.
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute("SELECT password_hash FROM user WHERE id = %s", (user.id,))
        row = cursor.fetchone()
    if not row or not password_utils.verify_password(data.current_password, row[0]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    current_status = _read_update_status()
    if current_status and current_status.get("state") == "running":
        raise HTTPException(status_code=409, detail="An update is already running")

    host_repo_path = os.environ.get("HOST_REPO_PATH")
    if not host_repo_path:
        raise HTTPException(status_code=500, detail="HOST_REPO_PATH is not configured")

    # Fail closed: no update starts without a good backup. Runs synchronously (mirrors
    # /system/database/backup's own existing behavior) rather than being handed off to the
    # updater container, since service-api already has DB credentials/network access and this
    # reuses tested code instead of re-implementing mysqldump in bash.
    try:
        backup = _perform_database_backup()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pre-update database backup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pre-update database backup failed: {e}")

    project_name = _project_name()
    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                f"{project_name}-updater-run",
                # Mounted at the *same* path inside the container as on the host -- not /repo.
                # docker compose (run from inside this container, but talking to the host's own
                # daemon over the bind-mounted socket) resolves docker-compose.yml's own relative
                # bind mounts (./nginx.conf, ./certs, ./setup/my.cnf) against its own cwd, and
                # that resolved path is handed to the HOST daemon -- if cwd were /repo, the host
                # would look for a literal /repo/nginx.conf on itself and (confirmed via a real
                # dry-run) silently create an empty directory there instead, then fail trying to
                # bind-mount that directory over the file nginx expects. Identical paths on both
                # sides sidesteps the translation entirely.
                "-v",
                f"{host_repo_path}:{host_repo_path}",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                "-v",
                f"{project_name}_update_status_data:/status",
                "-e",
                f"TARGET_TAG={data.target_tag}",
                "-e",
                f"BACKUP_TIMESTAMP={backup['timestamp']}",
                "-e",
                f"HOST_REPO_PATH={host_repo_path}",
                f"{project_name}-service-updater:latest",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except subprocess.SubprocessError as e:
        logger.error(f"Failed to launch updater container: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to launch updater container: {e}")

    if result.returncode != 0:
        logger.error(f"Failed to launch updater container: {result.stderr}")
        raise HTTPException(
            status_code=500, detail=f"Failed to launch updater container: {result.stderr}"
        )

    return {"message": "Update started", "target_tag": data.target_tag}


@router.get("/system/update/status")
async def get_update_status():
    status = _read_update_status()
    if status is None:
        return {"state": "idle"}
    return status


async def broadcast_update_status():
    """Re-publishes the updater container's status file over the existing WebSocket manager.
    The ephemeral updater container has no FastAPI app of its own and can't call
    manager.broadcast() directly -- polling here keeps its job to exactly "run the update, write
    a file," nothing network-facing. Backs off to a slower interval when idle so this doesn't
    burn CPU polling a static file between updates, which happen at most a few times a week."""
    while True:
        status = _read_update_status()
        interval = 15
        if status is not None:
            await manager.broadcast("update_status", status)
            if status.get("state") == "running":
                interval = 3
        await asyncio.sleep(interval)
