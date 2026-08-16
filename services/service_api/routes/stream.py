import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse

logger = logging.getLogger("ApiLog")

router = APIRouter(prefix="/api/stream")

CAMERA_URL = os.environ.get("STREAM_CAMERA_URL") or os.environ.get("CAMERA_URL")
if not CAMERA_URL:
    logger.warning(
        "STREAM_CAMERA_URL/CAMERA_URL not set — camera streaming endpoints will return 503"
    )

HLS_ROOT = Path("/tmp/hls")
HLS_CAMERA_ID = "camera"
HLS_SEGMENT_TIME = 2
HLS_LIST_SIZE = 4

_hls_state = {"process": None, "camera_id": None}
_hls_lock = asyncio.Lock()
_SEGMENT_RE = re.compile(r"^seg_\d+\.ts$")

STREAM_CONFIG = {
    "url": CAMERA_URL,
    "status": "configured" if CAMERA_URL else "unconfigured",
    "protocol": "rtsp",
}


@router.get("/camera")
async def stream_camera():
    if not CAMERA_URL:
        raise HTTPException(status_code=503, detail="Camera not configured")
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise HTTPException(status_code=503, detail="ffmpeg not available on server")

    async def generate():
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-rtsp_transport",
            "tcp",
            "-i",
            CAMERA_URL,
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "5",
            "-r",
            "15",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        boundary = b"frame"
        buf = b""
        frames = 0
        try:

            async def log_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    logger.warning(f"ffmpeg: {line.decode(errors='replace').strip()}")

            stderr_task = asyncio.create_task(log_stderr())
            try:
                while True:
                    chunk = await process.stdout.read(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(b"\xff\xd8")
                        if start == -1:
                            break
                        end = buf.find(b"\xff\xd9", start + 2)
                        if end == -1:
                            break
                        frame = buf[start : end + 2]
                        buf = buf[end + 2 :]
                        yield b"--" + boundary + b"\r\n"
                        yield b"Content-Type: image/jpeg\r\n"
                        yield b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                        yield b"\r\n"
                        yield frame
                        yield b"\r\n"
                        frames += 1
                logger.warning(f"ffmpeg stream ended after {frames} frames")
            finally:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            logger.warning(f"ffmpeg stream cancelled after {frames} frames")
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                rc = await asyncio.wait_for(process.wait(), timeout=5)
                logger.warning(f"ffmpeg exited with code {rc} after {frames} frames")
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/camera/config")
async def camera_config():
    return STREAM_CONFIG


@router.get("/camera/snapshot")
async def camera_snapshot():
    if not CAMERA_URL:
        raise HTTPException(status_code=503, detail="Camera not configured")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rtsp_transport",
                "tcp",
                "-i",
                CAMERA_URL,
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
    from starlette.responses import Response

    return Response(
        content=result.stdout,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


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


def _hls_dir() -> Path:
    return HLS_ROOT / HLS_CAMERA_ID


async def start_hls():
    if not CAMERA_URL:
        raise HTTPException(status_code=503, detail="Camera not configured")
    async with _hls_lock:
        proc = _hls_state.get("process")
        if proc and proc.returncode is None:
            return {"running": True, "camera_id": HLS_CAMERA_ID}

        if not await _ffmpeg_available():
            raise HTTPException(status_code=503, detail="ffmpeg not available on server")

        out_dir = _hls_dir()
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
            "-i",
            CAMERA_URL,
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
        _hls_state["process"] = proc
        _hls_state["camera_id"] = HLS_CAMERA_ID

        async def log_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                logger.warning(f"ffmpeg hls: {line.decode(errors='replace').strip()}")

        _hls_state["stderr_task"] = asyncio.create_task(log_stderr())

        playlist = out_dir / "index.m3u8"
        for _ in range(40):
            if playlist.exists():
                break
            if proc.returncode is not None:
                break
            await asyncio.sleep(0.25)
        if not playlist.exists():
            stderr_task = _hls_state.pop("stderr_task", None)
            if stderr_task:
                stderr_task.cancel()
            _hls_state["process"] = None
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
            raise HTTPException(
                status_code=502,
                detail="failed to start HLS stream (no playlist produced)",
            )
        return {"running": True, "camera_id": HLS_CAMERA_ID}


async def stop_hls():
    async with _hls_lock:
        proc = _hls_state.get("process")
        _hls_state["process"] = None
        stderr_task = _hls_state.pop("stderr_task", None)
        if stderr_task:
            stderr_task.cancel()
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
        out_dir = _hls_dir()
        if out_dir.exists():
            for f in out_dir.glob("*"):
                try:
                    f.unlink()
                except OSError:
                    pass
    return {"running": False}


async def hls_status():
    proc = _hls_state.get("process")
    running = proc is not None and proc.returncode is None
    out_dir = _hls_dir()
    playlist = out_dir / "index.m3u8"
    playlist_exists = playlist.exists() and playlist.stat().st_size > 0
    segments = sorted(out_dir.glob("seg_*.ts")) if out_dir.exists() else []
    return {
        "running": running,
        "camera_id": HLS_CAMERA_ID,
        "playlist_exists": playlist_exists,
        "segment_count": len(segments),
        "last_segment": segments[-1].name if segments else None,
    }


@router.post("/hls/start")
async def hls_start():
    return await start_hls()


@router.post("/hls/stop")
async def hls_stop():
    return await stop_hls()


@router.get("/hls/status")
async def hls_get_status():
    return await hls_status()


@router.get("/hls/index.m3u8")
async def hls_playlist():
    status = await hls_status()
    if not status["running"] or not status["playlist_exists"]:
        raise HTTPException(status_code=503, detail="HLS stream not active")
    playlist = _hls_dir() / "index.m3u8"
    return FileResponse(
        playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/hls/{filename}")
async def hls_segment(filename: str):
    if not _SEGMENT_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid segment name")
    segment = _hls_dir() / filename
    if not segment.exists():
        raise HTTPException(status_code=404, detail="segment not found")
    return FileResponse(
        segment,
        media_type="video/mp2t",
        headers={"Cache-Control": "no-cache, max-age=2"},
    )
