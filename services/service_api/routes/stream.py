import asyncio
import logging
import subprocess

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

logger = logging.getLogger("ApiLog")

router = APIRouter(prefix="/api/stream")

CAMERA_URL = (
    "rtsp://armageddion%40gmail.com:"
    "qweQWE123%21%40%23@192.168.2.226:554/stream1"
)

STREAM_CONFIG = {
    "url": CAMERA_URL,
    "status": "configured",
    "protocol": "rtsp",
    "host": "192.168.2.226",
    "port": 554,
    "path": "/stream1",
}


@router.get("/camera")
async def stream_camera():
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
            "-rtsp_transport", "tcp",
            "-i", CAMERA_URL,
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "5",
            "-r", "15",
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
                        frame = buf[start:end + 2]
                        buf = buf[end + 2:]
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
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-i", CAMERA_URL,
                "-vframes", "1",
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "3",
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
