# Real-Time Camera Feed Streaming

## Status: ✅ IMPLEMENTED (HLS via ffmpeg, device-registry-backed, multi-camera)

> RTSP is remuxed to HLS (copy codec) by a background ffmpeg process and served as
> TS segments + m3u8 playlist by FastAPI. The frontend plays it in a `<video>` element
> via hls.js (native HLS on Safari). Camera source config lives on the `device` row
> (`device_type = 'camera'`, `stream_url` column) instead of an env var, so any number
> of cameras can be registered and the Nexus panel lets the user pick/toggle between them.

---

## Implemented

### Schema: `device.stream_url`
- Migration `0021_camera_stream_url.py` / `migration_020_camera_stream_url.sql` adds a
  nullable `stream_url VARCHAR(512)` column to `device`.
- Write-only from the API's perspective: `GET /api/devices` (and its websocket broadcast,
  which reaches every connected client) never returns the raw URL — only a `has_stream`
  boolean. Avoids leaking RTSP credentials broadly.

### Backend: `services/service_api/routes/stream.py`
- **Single-active-stream**: only one ffmpeg HLS transcode runs at a time; starting a new
  camera auto-stops whichever `device_id` was previously active.
- `GET /api/stream/cameras` — lists `device` rows where `device_type = 'camera'` and
  `stream_url IS NOT NULL` (id/name/running only, never the raw URL)
- `POST /api/stream/hls/{device_id}/start` / `stop` / `GET .../status`
- `GET /api/stream/hls/{device_id}/index.m3u8` — playlist (no-cache)
- `GET /api/stream/hls/{device_id}/{filename}` — `.ts` segments (regex-validated filename)
- `GET /api/stream/camera/{device_id}/snapshot` — one-shot JPEG snapshot
- Each camera's `stream_url` is looked up from `device`/`device_types` per request; the
  legacy MJPEG multipart endpoint (`GET /api/stream/camera`, unused by the UI) and the
  `STREAM_CAMERA_URL`/`CAMERA_URL` env var are both removed
- ffmpeg process state guarded by an `asyncio.Lock`, keyed per `device_id`; stderr streamed to logs

### Backend: `services/service_api/routes/devices.py` + `models.py`
- `DeviceCreate`/`DeviceUpdate` accept `stream_url`, validated as `rtsp://`/`rtsps://`-prefixed
- Loosely enforced — not tied to `device_type == 'camera'` at the DB layer, matching how
  `position` is accepted on any device type; the frontend gates visibility

### Frontend: `src/components/CameraStream.jsx`
- Fetches `GET /api/stream/cameras` on mount; renders a tab strip to select/toggle between
  configured cameras (only shown when more than one is available)
- `<video>` HLS playback via hls.js (v1.6.17), Safari fallback to native HLS
- Switching cameras stops the previous backend stream and starts the newly selected one
- Status indicator (connecting/connected/error), show/hide toggle, snapshot capture, reconnect
- "NO CAMERAS CONFIGURED" empty state when no device has both `device_type = 'camera'` and a `stream_url`
- Integrated via `src/pages/Nexus.jsx`

### Frontend: `src/components/DeviceRegistry.jsx`
- Editing a `camera`-type device shows a `stream_url` input (write-only — never pre-filled
  with the existing value; left blank on save, the existing URL is untouched)
- Read-only card shows a `Stream: configured/not configured` badge for camera-type devices

### Camera registration
- C200 (Tapo) is device ID 79 in the `device` table, IP `192.168.2.226` — discovered via LAN
  ARP scan. To activate streaming: Domain > Devices > edit "C200" > set Type to `camera` >
  set Stream URL (`rtsp://<user>:<pass>@192.168.2.226:554/stream1`) > Save. No `/etc/hosts`
  entry needed (raw IP).

---

## Not Yet Done (Future Options)

### Phase: Low-latency / scale (WebRTC)
- HLS adds ~2-4s glass-to-glass latency. If <500ms is required, evaluate WebRTC
  (Janus/mediasoup SFU) with TURN/STUN
- `camera_streams` table for stream lifecycle/health (status, started_at, last_frame_at)
- `camera_status` WebSocket events
- Concurrent multi-camera streaming (currently single-active-stream by design — switching
  cameras stops the previous ffmpeg process rather than running them in parallel)

### Phase: Recording & Playback (Future)
- Segmented MP4 recording pipeline (continuous, motion-triggered, time-based)
- Video archive browser + timeline scrubber
- Storage management / retention policy

### Phase: Computer Vision (Future)
- OpenCV/TFLite motion/person/vehicle detection with bounding boxes
- Motion-based recording triggers → Kafka → notifications

---

## Implementation Notes
- HLS uses `-c:v copy` remux (no video transcode) + `-c:a aac` audio transcode. The
  C200 emits **PCM ALAW** audio which browsers cannot decode when muxed raw into
  MPEG-TS (hls.js showed a black frame); transcoding audio to AAC fixes playback.
  If a source is H.265, switch to full video transcode
  (`-c:v libx264 -preset veryfast -tune zerolatency -c:a aac`)
- FFmpeg must be installed inside the service_api image for transcoding
- `todo_iot.md` Phase 15 covers device registration — this builds on top of that
