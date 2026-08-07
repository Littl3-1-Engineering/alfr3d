# Real-Time Camera Feed Streaming

## Status: ✅ IMPLEMENTED (MJPEG proxy via ffmpeg)

> The original plan targeted WebRTC/HLS. In practice a simpler **RTSP → MJPEG proxy**
> was built and shipped: FastAPI proxies the RTSP stream through an ffmpeg subprocess
> to an MJPEG `<img>` feed in a side panel. WebRTC/HLS remains a future upgrade path
> if lower latency or multi-viewer scale is needed.

---

## Implemented

### Backend: `services/service_api/routes/stream.py`
- `GET /api/stream/camera` — FastAPI streaming endpoint that proxies RTSP → MJPEG via an ffmpeg subprocess (one-shot, `-f mjpeg` output)
- `GET /api/stream/camera/config` — returns the configured RTSP URL for the frontend
- `CAMERA_URL` configurable via `STREAM_CAMERA_URL` / `CAMERA_URL` env var

### Frontend: `src/components/CameraStream.jsx`
- Collapsible side panel on the Nexus page with `<img>` MJPEG display
- Status indicator (connecting/connected/error)
- Show/hide toggle, snapshot capture, reconnect button
- Integrated via `src/pages/Nexus.jsx`

### Camera registration
- RTSP camera already in DB as device ID 79 ("C200", type HW, IP `192.168.2.226`) via LAN scan
- No `/etc/hosts` entry needed — `CAMERA_URL` uses the raw IP

---

## Not Yet Done (Future Options)

### Phase: WebRTC / HLS
- If low-latency multi-viewer streaming is required, evaluate:
  - **HLS** — ffmpeg RTSP → HLS segments + m3u8 playlist, plays natively via `<video>`
  - **WebRTC** — Janus/mediasoup SFU for ~200ms latency with TURN/STUN
- `camera_streams` table for stream lifecycle/health (status, started_at, last_frame_at)
- `camera_status` WebSocket events

### Phase: Recording & Playback (Future)
- Segmented MP4 recording pipeline (continuous, motion-triggered, time-based)
- Video archive browser + timeline scrubber
- Storage management / retention policy

### Phase: Computer Vision (Future)
- OpenCV/TFLite motion/person/vehicle detection with bounding boxes
- Motion-based recording triggers → Kafka → notifications

---

## Implementation Notes
- RTSP source: `c200` camera at `192.168.2.226`
- FFmpeg must be installed inside the service_api image for transcoding
- `todo_iot.md` Phase 15 covers device registration — this builds on top of that
