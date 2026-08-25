"""Audio file serving routes."""

import os
import re
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["audio"])

# Allowlist the filename outright rather than blocklisting "/" and ".." -- a single
# path segment of safe characters plus a known extension, so there's nothing left
# to sanitize between here and the filesystem join below.
_AUDIO_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.(mp3|wav)$")


@router.api_route("/audio/{filename}", methods=["GET", "HEAD"])
async def get_audio(filename: str):
    logger.info(f"Audio request received for filename: {filename}")

    if not _AUDIO_FILENAME_RE.match(filename):
        logger.error(f"Invalid filename: {filename}")
        raise HTTPException(status_code=400, detail="Invalid filename")

    audio_path = os.path.join("/tmp/audio", filename)
    if not os.path.exists(audio_path):
        logger.warning(f"Audio file not found: {audio_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")
    logger.info(f"Serving audio file: {audio_path}")

    if filename.endswith(".wav"):
        return FileResponse(audio_path, media_type="audio/wav")
    else:
        return FileResponse(audio_path, media_type="audio/mpeg")
