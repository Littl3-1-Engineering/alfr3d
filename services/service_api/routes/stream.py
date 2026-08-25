import asyncio
import logging
import re
import subprocess
import time
from pathlib import Path

import pymysql
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import Response

from dependencies import db_connection
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")

router = APIRouter(prefix="/api/stream")

HLS_ROOT = Path("/tmp/hls")
HLS_SEGMENT_TIME = 2
HLS_LIST_SIZE = 4

# Single-active-stream: only one camera transcodes at a time. Starting a new one
# stops whichever device_id was previously active.
_hls_state: dict[int, dict] = {}
_active_device_id: int | None = None
_hls_lock = asyncio.Lock()
_SEGMENT_RE = re.compile(r"^seg_\d+\.ts$")

# ffmpeg can hang indefinitely on a stalled RTSP read without exiting or logging
# anything (-timeout below mitigates that at the ffmpeg level), so this is a
# second line of defense: if the process is alive but hasn't written a new
# segment in a while, treat the stream as hung and restart it.
_STALE_AFTER = HLS_SEGMENT_TIME * HLS_LIST_SIZE + 10


def _stream_is_stale(out_dir: Path) -> bool:
    segments = sorted(out_dir.glob("seg_*.ts")) if out_dir.exists() else []
    if not segments:
        return False
    newest = max(f.stat().st_mtime for f in segments)
    return (time.time() - newest) > _STALE_AFTER


def _get_camera(device_id: int) -> dict:
    """Look up a camera-type device's stream_url, or raise the appropriate HTTPException."""
    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            """
            SELECT d.id, d.name, d.stream_url
            FROM device d
            JOIN device_types dt ON d.device_type = dt.id
            WHERE d.id = %s AND dt.type = 'camera'
            """,
            (device_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera device not found")
    if not row["stream_url"]:
        raise HTTPException(status_code=503, detail="Camera not configured")
    return row


@router.get("/cameras")
async def list_cameras():
    with db_connection() as db:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            """
            SELECT d.id, d.name
            FROM device d
            JOIN device_types dt ON d.device_type = dt.id
            WHERE dt.type = 'camera' AND d.stream_url IS NOT NULL
            ORDER BY d.name
            """
        )
        rows = cursor.fetchall()
    return [
        {"id": row["id"], "name": row["name"], "running": row["id"] == _active_device_id}
        for row in rows
    ]


async def _ffmpeg_available() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        return proc.returncode == 0
    except (FileNotFoundError, asyncio.TimeoutError):
        return False


def _hls_dir(device_id: int) -> Path:
    candidate = (HLS_ROOT / str(device_id)).resolve()
    if candidate.parent != HLS_ROOT.resolve():
        raise HTTPException(status_code=400, detail="invalid device id")
    return candidate


async def _stop_hls_locked(device_id: int):
    """Stop the ffmpeg process for device_id. Caller must hold _hls_lock."""
    global _active_device_id
    state = _hls_state.pop(device_id, None)
    if _active_device_id == device_id:
        _active_device_id = None
    if state is None:
        return
    stderr_task = state.get("stderr_task")
    if stderr_task:
        stderr_task.cancel()
    proc = state.get("process")
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
    out_dir = _hls_dir(device_id)
    if out_dir.exists():
        for f in out_dir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass


async def _start_locked(device_id: int) -> dict:
    """Spawn ffmpeg for device_id. Caller must hold _hls_lock."""
    global _active_device_id
    camera = _get_camera(device_id)

    if _active_device_id is not None and _active_device_id != device_id:
        await _stop_hls_locked(_active_device_id)

    if not await _ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not available on server")

    out_dir = _hls_dir(device_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*"):
        f.unlink()

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        # Fail fast instead of hanging forever if the camera stops responding
        # mid-stream (blocking network reads don't otherwise time out).
        "-timeout",
        "15000000",
        "-i",
        camera["stream_url"],
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-f",
        "hls",
        "-hls_time",
        str(HLS_SEGMENT_TIME),
        "-hls_list_size",
        str(HLS_LIST_SIZE),
        "-hls_flags",
        "delete_segments+append_list",
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        str(out_dir / "seg_%05d.ts"),
        str(out_dir / "index.m3u8"),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    async def log_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            logger.warning(f"ffmpeg hls[{device_id}]: {line.decode(errors='replace').strip()}")

    stderr_task = asyncio.create_task(log_stderr())
    _hls_state[device_id] = {"process": proc, "stderr_task": stderr_task}
    _active_device_id = device_id

    playlist = out_dir / "index.m3u8"
    for _ in range(40):
        if playlist.exists():
            break
        if proc.returncode is not None:
            break
        await asyncio.sleep(0.25)
    if not playlist.exists():
        await _stop_hls_locked(device_id)
        raise HTTPException(
            status_code=502,
            detail="failed to start HLS stream (no playlist produced)",
        )
    return {"running": True, "camera_id": device_id}


async def start_hls(device_id: int):
    async with _hls_lock:
        state = _hls_state.get(device_id)
        if state and state["process"].returncode is None:
            if not _stream_is_stale(_hls_dir(device_id)):
                return {"running": True, "camera_id": device_id}
            logger.warning(f"ffmpeg hls[{device_id}]: stream stalled, restarting")
            await _stop_hls_locked(device_id)
        return await _start_locked(device_id)


async def stop_hls(device_id: int):
    async with _hls_lock:
        await _stop_hls_locked(device_id)
    return {"running": False}


async def hls_status(device_id: int):
    state = _hls_state.get(device_id)
    proc = state.get("process") if state else None
    running = proc is not None and proc.returncode is None
    out_dir = _hls_dir(device_id)
    if running and _stream_is_stale(out_dir):
        async with _hls_lock:
            state = _hls_state.get(device_id)
            proc = state.get("process") if state else None
            running = proc is not None and proc.returncode is None
            if running and _stream_is_stale(out_dir):
                logger.warning(f"ffmpeg hls[{device_id}]: stream stalled, auto-restarting")
                await _stop_hls_locked(device_id)
                try:
                    await _start_locked(device_id)
                    running = True
                except HTTPException:
                    running = False
    playlist = out_dir / "index.m3u8"
    playlist_exists = playlist.exists() and playlist.stat().st_size > 0
    segments = sorted(out_dir.glob("seg_*.ts")) if out_dir.exists() else []
    return {
        "running": running,
        "camera_id": device_id,
        "playlist_exists": playlist_exists,
        "segment_count": len(segments),
        "last_segment": segments[-1].name if segments else None,
    }


@router.post("/hls/{device_id}/start")
async def hls_start(device_id: int, _perm=Depends(require_permission("stream", "start"))):
    return await start_hls(device_id)


@router.post("/hls/{device_id}/stop")
async def hls_stop(device_id: int, _perm=Depends(require_permission("stream", "stop"))):
    return await stop_hls(device_id)


@router.get("/hls/{device_id}/status")
async def hls_get_status(device_id: int):
    return await hls_status(device_id)


@router.get("/hls/{device_id}/index.m3u8")
async def hls_playlist(device_id: int):
    status = await hls_status(device_id)
    if not status["running"] or not status["playlist_exists"]:
        raise HTTPException(status_code=503, detail="HLS stream not active")
    playlist = _hls_dir(device_id) / "index.m3u8"
    return FileResponse(
        playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/hls/{device_id}/{filename}")
async def hls_segment(device_id: int, filename: str):
    if not _SEGMENT_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid segment name")
    hls_dir = _hls_dir(device_id)
    segment = (hls_dir / filename).resolve()
    if segment.parent != hls_dir:
        raise HTTPException(status_code=400, detail="invalid segment name")
    if not segment.exists():
        raise HTTPException(status_code=404, detail="segment not found")
    return FileResponse(
        segment,
        media_type="video/mp2t",
        headers={"Cache-Control": "no-cache, max-age=2"},
    )


@router.get("/camera/{device_id}/snapshot")
async def camera_snapshot(device_id: int):
    camera = _get_camera(device_id)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rtsp_transport",
                "tcp",
                "-i",
                camera["stream_url"],
                "-vframes",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "3",
                "pipe:1",
            ],
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise HTTPException(status_code=503, detail="ffmpeg not available on server")
    if result.returncode != 0 or not result.stdout:
        raise HTTPException(status_code=502, detail="failed to capture snapshot")

    return Response(
        content=result.stdout,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )
