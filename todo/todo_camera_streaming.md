# Real-Time Camera Feed Streaming

## Status: ✅ IMPLEMENTED (HLS via ffmpeg)

> RTSP is remuxed to HLS (copy codec) by a background ffmpeg process and served as
> TS segments + m3u8 playlist by FastAPI. The frontend plays it in a `<video>` element
> via hls.js (native HLS on Safari). The original one-shot MJPEG proxy endpoint remains
> available but the frontend now uses HLS for smooth multi-viewer playback.

---

## Implemented

### Backend: `services/service_api/routes/stream.py`
- **HLS pipeline** — `start_hls()` spawns a persistent ffmpeg process remuxing RTSP → HLS
  (`-c:v copy -c:a copy`, 2s segments, 4-segment rolling list) to `/tmp/hls/camera/`;
  `stop_hls()` terminates it; `hls_status()` reports health
- `POST /api/stream/hls/start` / `POST /api/stream/hls/stop` / `GET /api/stream/hls/status`
- `GET /api/stream/hls/index.m3u8` — serves the playlist (no-cache)
- `GET /api/stream/hls/segment/{filename}` — serves `.ts` segments (regex-validated path)
- `GET /api/stream/camera` — legacy RTSP → MJPEG streaming endpoint (kept, unused by UI)
- `GET /api/stream/camera/config` — returns the configured RTSP URL for the frontend
- `GET /api/stream/camera/snapshot` — one-shot JPEG snapshot
- `CAMERA_URL` configurable via `STREAM_CAMERA_URL` / `CAMERA_URL` env var
- ffmpeg background process state guarded by an `asyncio.Lock`; stderr streamed to logs

### Frontend: `src/components/CameraStream.jsx`
- Collapsible side panel on the Nexus page with `<video>` HLS playback via **hls.js** (v1.6.17)
- Starts backend HLS process on mount, stops it on unmount
- Safari fallback to native HLS (`application/vnd.apple.mpegurl`)
- Status indicator (connecting/connected/error), show/hide toggle, snapshot capture, reconnect button
- Integrated via `src/pages/Nexus.jsx`

### Camera registration
- RTSP camera already in DB as device ID 79 ("C200", type HW, IP `192.168.2.226`) via LAN scan
- No `/etc/hosts` entry needed — `CAMERA_URL` uses the raw IP

---

## Not Yet Done (Future Options)

### Phase: Low-latency / scale (WebRTC)
- HLS adds ~2-4s glass-to-glass latency. If <500ms is required, evaluate WebRTC
  (Janus/mediasoup SFU) with TURN/STUN
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
- HLS uses `-c copy` remux (no transcode) — requires the camera to emit H.264 video;
  if the source is H.265 or has unsupported audio, switch to transcode
  (`-c:v libx264 -preset veryfast -tune zerolatency -c:a aac`)
- FFmpeg must be installed inside the service_api image for transcoding
- `todo_iot.md` Phase 15 covers device registration — this builds on top of that

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
