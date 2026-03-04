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

### To Do
- Run migration to add columns to smarthome_devices table:
  - source (VARCHAR: 'homeassistant' or 'smartthings')
  - mac_address
  - ha_entity_id
  - st_device_id
- Add config entries for IoT settings

---

## Phase 3: Home Assistant Integration

### To Do
- Create `ha_utils.py` in service_device
- API endpoints:
  - GET /api/iot/ha/status
  - GET /api/iot/ha/devices
  - POST /api/iot/ha/devices/<entity_id>/control
  - PUT /api/iot/ha/config
  - POST /api/iot/ha/sync

---

## Phase 4: SmartThings Integration

### To Do
- Create `st_utils.py` in service_device
- API endpoints:
  - GET /api/iot/st/status
  - GET /api/iot/st/devices
  - POST /api/iot/st/devices/<device_id>/control
  - PUT /api/iot/st/config
  - POST /api/iot/st/sync

---

## Phase 5: Unified IoT Layer

### To Do
- Unified API endpoints:
  - GET /api/iot/status
  - GET /api/iot/devices
  - POST /api/iot/devices/<id>/control
  - GET /api/iot/providers
  - PUT /api/iot/provider
- Merge by MAC address logic with device table

---

## Notes
- HA URL and token configured through frontend (stored in config table)
- SmartThings uses PAT (Personal Access Token)
- User selects default provider (HA or ST)
- Devices merged by MAC address with local device table
