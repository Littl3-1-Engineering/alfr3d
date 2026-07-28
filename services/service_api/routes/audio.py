"""Audio file serving routes."""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["audio"])


@router.api_route("/audio/{filename}", methods=["GET", "HEAD"])
async def get_audio(filename: str):
    logger.info(f"Audio request received for filename: {filename}")

    if not (filename.endswith(".mp3") or filename.endswith(".wav")):
        logger.error(f"Invalid file type for filename: {filename}")
        raise HTTPException(status_code=400, detail="Invalid file type")

    if ".." in filename or "/" in filename:
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
