# Plan to Implement IoT Integration (Home Assistant + SmartThings)

## Phase 1: REMOVED GOOGLE HOME ✓

### Completed
- Deleted `google_smarthome_utils.py`
- Deleted `test_google_smarthome_utils.py`
- Deleted `google-smarthome-sa.json` credentials
- Removed API endpoints: `/api/smarthome/*`
- Removed Kafka handlers for Google actions
- Updated Frontend: Replaced Google Assistant with HA/ST in Integrations.jsx
- Updated ControlBlade.jsx to use new `/api/iot/*` endpoints
- Removed google-smarthome-sa.json volume from docker-compose.yml

---

## Phase 2: Database Schema Updates ✓

### Completed
- Migration `migration_002_iot.sql` adds columns to smarthome_devices table:
  - source (VARCHAR: 'homeassistant' or 'smartthings')
  - mac_address
  - ha_entity_id
  - st_device_id
- Config entries: iot_provider, ha_url, ha_token, st_pat

---

## Phase 3: Home Assistant Integration ✓

### Completed
- Created `services/common/ha_utils.py`
- API endpoints implemented in service_api/app.py:
  - GET /api/iot/ha/status
  - GET /api/iot/ha/devices
  - POST /api/iot/ha/devices/<entity_id>/control
  - PUT /api/iot/ha/config
  - POST /api/iot/ha/sync

---

## Phase 4: SmartThings Integration ✓

### Completed
- Created `services/common/st_utils.py`
- API endpoints implemented in service_api/app.py:
  - GET /api/iot/st/status
  - GET /api/iot/st/devices
  - POST /api/iot/st/devices/<device_id>/control
  - PUT /api/iot/st/config
  - POST /api/iot/st/sync

---

## Phase 5: Unified IoT Layer ✓

### Completed
- Unified API endpoints in service_api/app.py:
  - GET /api/iot/status
  - GET /api/iot/devices
  - POST /api/iot/devices/<id>/control
  - GET /api/iot/providers
  - PUT /api/iot/provider
- Merge by MAC address logic with device table
- Devices displayed on Blueprint alongside local devices
- 15-minute periodic sync via daemon Kafka messages

---

## Phase 6: Device Types Expansion ✓

### Completed
- Migration `migration_007_device_types_expansion.sql` adds to `device_types`:
  - fan, climate, cover, lock, media_player, sensor, binary_sensor, camera

---

## Phase 7: FK Relationship & Auto-Linking ✓

### Completed
- Migration `migration_008_iot_device_link.sql`:
  - Added `device_id` column to `smarthome_devices` table
  - Added FK constraint and index
- Updated `ha_utils.sync_ha_devices()` to auto-link by MAC, create device if not found
- Updated `st_utils.sync_st_devices()` similarly
- Updated `/api/iot/devices` endpoint to use FK join

---

## Phase 8: Expanded Device Controls ✓

### Completed
- Updated ControlBlade.jsx with device-type-specific controls:
  - 8.1 Climate: Temperature up/down, current/target display
  - 8.2 Lock: Lock/unlock toggle with visual state
  - 8.3 Fan: Power toggle + speed control (off/low/medium/high)
  - 8.4 Cover: Position slider, open/close buttons
  - 8.5 Media Player: Play/pause, volume slider
- Updated `/api/iot/devices/{id}/control` API to handle all device type commands

---

## Phase 9: Sensor Display ✓

### Completed
- Updated ha_utils.py to fetch sensor/binary_sensor domains from HA
- Updated Blueprint.jsx with sensor icons (Droplets, Activity, Camera, Gauge)
- Added sensor display in ControlBlade (temperature, humidity, current, battery)

---

## Phase 10: Device Linking UI ✓

### Completed
- Added `/api/iot/devices/{id}/link` PUT endpoint for linking/unlinking
- Added "SMARTHOME DEVICES" section in DeviceRegistry.jsx
- Shows linked/unlinked status with warning icons
- Link modal to select target alfr3d device
- Unlink button to remove link
- Updated Blueprint.jsx to use linked device type for icons

---

## Phase 11: Modal Fixes ✓

### Completed
- Added `.glass` CSS class with solid background in index.css
- ControlBlade modal now less transparent (95% opacity)

---

## Phase 13: Real-time State Updates ✓

### Goal
Implement WebSocket for real-time device state changes instead of polling.

### Completed
- Added `broadcast_iot_devices()` background task in `routes/iot.py` (30s interval)
- Added `fetch_iot_devices_data()` reusable function for consistent IoT device queries
- WebSocket broadcast after device control, link, and unlink operations
- Refactored `GET /api/iot/devices` to reuse shared fetch function
- Frontend `Blueprint.jsx`: Subscribes to `iot_devices` WebSocket events, merges IoT devices with local devices in real-time
- Frontend `DeviceRegistry.jsx`: Subscribes to `iot_devices` and `devices` WebSocket events for live updates
- WebSocket events: `devices` (5s broadcast), `users` (10s broadcast), `iot_devices` (30s broadcast)
- Removed HTTP polling for users/devices from Core.jsx, OnlineUsers.jsx, GuestRoster.jsx

---

## Phase 14: Automations/Routines Engine (Future)

### Goal
Allow users to create automations like "turn on light at sunset".

### Tasks
- Create `automations` table
- Create automation builder UI
- Support triggers: time, device state, sun position
- Support actions: control device, send notification, etc.
- Execute via daemon service

---

## Migrations Applied

| Migration | File | Description |
|-----------|------|-------------|
| 002 | migration_002_iot.sql | IoT integration (smarthome_devices, device_command_history) |
| 003 | migration_003_routines.sql | Routine management |
| 004 | migration_004_personality.sql | Personality settings |
| 005 | migration_005_indexes.sql | Database indexes |
| 006 | migration_006_personality_context.sql | Context tracking |
| 007 | migration_007_device_types_expansion.sql | Device types (fan, climate, cover, lock, media_player, sensor, etc.) |
| 008 | migration_008_iot_device_link.sql | FK relationship between smarthome_devices and device tables |
| 016 | migration_016_iot_device_cleanup.sql | Remove auto-created device rows (IP='0.0.0.0') from past syncs |

---

---

## Phase 15: RTSP Camera as Smart Device ✓

### Goal
Register the RTSP camera (`c200`) as a `camera`-type device in the device registry so it appears on the Blueprint with a camera icon and links to its RTSP stream.

### Completed
- Camera already registered in DB as device ID 79 ("C200", type HW, IP `192.168.2.226`) via LAN scan — no `/etc/hosts` entry needed
- `services/service_api/routes/stream.py` implements RTSP → MJPEG proxy (`GET /api/stream/camera` + `/api/stream/camera/config`)
- `CameraStream.jsx` side panel with MJPEG display, snapshot, reconnect (integrated in Nexus)
- See `todo/todo_camera_streaming.md` for details and future WebRTC/HLS options

---

## Phase 16: HA Device Matching & Domain Page Filtering ✓

### Goal
Devices integrated via HA should be matched to devices in the `device` table. Unmatched HA devices should NOT auto-create `device` table records and should NOT appear on the Domain/Blueprint page (too many HA devices to show all).

### Completed
- Stopped auto-creating `device` records in `sync_ha_devices()` (ha_utils.py) and `sync_st_devices()` (st_utils.py) — unmatched HA/ST devices stay in `smarthome_devices` only (device_id = NULL)
- Added `?linked=true/false` filter to `GET /api/iot/devices` (routes/iot.py) — defaults to all for DeviceRegistry/Routines
- `Blueprint.jsx` now merges only linked IoT devices (`mergeWithIot` filters `iot.linked`) — unlinked HA devices no longer flood the Domain/Blueprint page
- Removed dead unlinked-warning UI + unused `AlertTriangle` import from Blueprint.jsx
- Cleanup migration `setup/migration_016_iot_device_cleanup.sql` (alembic `0017`) deletes existing auto-created device rows (IP='0.0.0.0') and unlinks them, respecting FK order (device_history → smarthome_devices → device)
- ✅ Migration `0017` applied to live DB on 2026-08-07 (`docker compose run --rm migrate`) — 0 junk rows remain; `0001_baseline` made idempotent so `migrate` passes on existing DBs

### Notes
- Unlinked HA devices are still managed/linkable in Domain → Devices → SMARTHOME DEVICES (DeviceRegistry keeps showing all)
- Manual links persist across sync (COALESCE preserves existing device_id)
- Migrations table below needs `016` row added

---

## Notes
- HA URL and token configured through frontend (stored in config table)
- SmartThings uses PAT (Personal Access Token)
- User selects default provider (HA or ST)
- LAN scan (service_device) adds devices to `device` table
- HA/ST sync populates `smarthome_devices` and auto-links via device_id FK
- If MAC not found in device table, device stays unlinked (no device record created)
- Device linking UI in Domain → Devices → SMARTHOME DEVICES section
- Linked devices show "LINKED" status in blue
- Unlinked devices show warning icon - must link before use on Blueprint
- device_types expanded to support all HA/ST domains
