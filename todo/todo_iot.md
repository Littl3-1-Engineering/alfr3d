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

## Phase 2: Database Schema Updates

### Completed
- Migration `migration_002_iot.sql` adds columns to smarthome_devices table:
  - source (VARCHAR: 'homeassistant' or 'smartthings')
  - mac_address
  - ha_entity_id
  - st_device_id
- Config entries: iot_provider, ha_url, ha_token, st_pat

---

## Phase 3: Home Assistant Integration

### Completed
- Created `services/service_device/ha_utils.py`
- API endpoints implemented in service_api/app.py:
  - GET /api/iot/ha/status
  - GET /api/iot/ha/devices
  - POST /api/iot/ha/devices/<entity_id>/control
  - PUT /api/iot/ha/config
  - POST /api/iot/ha/sync

---

## Phase 4: SmartThings Integration

### Completed
- Created `services/service_device/st_utils.py`
- API endpoints implemented in service_api/app.py:
  - GET /api/iot/st/status
  - GET /api/iot/st/devices
  - POST /api/iot/st/devices/<device_id>/control
  - PUT /api/iot/st/config
  - POST /api/iot/st/sync

---

## Phase 5: Unified IoT Layer

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

## Notes
- HA URL and token configured through frontend (stored in config table)
- SmartThings uses PAT (Personal Access Token)
- User selects default provider (HA or ST)
- Devices merged by MAC address with local device table
