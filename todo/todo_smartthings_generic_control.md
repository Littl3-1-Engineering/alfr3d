# Todo: Wire SmartThings into the Generic IoT Control Endpoint

## Status: 🔲 Not started (found 2026-08-24 during the IoT central-control audit, split out from `todo_iot_central_control.md`)

## Goal

`POST /api/iot/devices/{id}/control` (`services/service_api/routes/iot.py`, `control_iot_device()`)
is documented in `todo_iot.md` Phase 5 as the unified front door for Home Assistant **and**
SmartThings devices, and is what `ControlBlade.jsx` calls for every device shown on the
Blueprint. In the actual code it only branches on `source == "homeassistant"` or `"esphome"` —
a SmartThings-sourced device falls through to the `else` branch and gets a 400 "Unsupported
source or device" on every single command. Clicking any ST device on the Blueprint and trying to
control it fails outright today.

## Why this is more than a missing `elif` branch

- **Different command model.** HA/ESPHome are keyed off `domain` (from `ha_entity_id`'s
  `light.`/`switch.`/... prefix) + a service name + a flat params dict — `ControlBlade.jsx`'s
  generic vocabulary (`turn_on`, `set_brightness`, `volume_set`, ...) maps onto that reasonably
  directly (see `ha_utils.translate_generic_control_params()`, added 2026-08-24). SmartThings'
  own control primitive (`st_utils.st_control_device(device_id, capability, command, args)`,
  already used by the ST-specific route `/iot/st/devices/{id}/control`) is
  capability+command+args — e.g. `switch`/`on`, `switchLevel`/`setLevel`/`[level]`,
  `lock`/`lock`. There's no existing mapping from ControlBlade's generic command vocabulary to
  ST capabilities; it needs to be built from scratch, one capability at a time.
- **`device_type` isn't normalized for ST rows.** `st_utils.sync_st_devices()` sets
  `smarthome_devices.device_type` from ST's raw `deviceTypeName`/`typeName` (e.g. "Samsung OCF
  Switch"), not the light/switch/fan/climate/cover/lock/media_player/sensor/binary_sensor
  vocabulary HA sync and ESPHome sync both populate and that `ControlBlade.jsx`'s
  `renderDeviceControls()` switches on. Even once the control endpoint accepts ST devices, an ST
  switch or light almost certainly renders as the generic power-toggle fallback today rather than
  its real control surface, because its `device_type` string doesn't match any case in that
  switch statement. This needs fixing in `sync_st_devices()` (map ST's device-type/capability
  list to the normalized vocabulary) before or alongside the control-endpoint fix, or the
  endpoint fix alone won't produce correct UI.

## Suggested approach (sketch — needs a scoping pass, not sized yet)

1. In `sync_st_devices()` (`services/common/st_utils.py`), derive a normalized `device_type` from
   the device's ST capability list (e.g. presence of `switchLevel` + `colorControl`/`colorTemperature`
   → `light`; bare `switch` → `switch`; `lock` → `lock`; `thermostatMode` → `climate`;
   `windowShade` → `cover`; `mediaPlayback`/`audioVolume` → `media_player`) instead of storing the
   raw `deviceTypeName` label. Check whether any existing code already reads the raw value and
   would break if it changed.
2. Add a `source == "smartthings"` branch to `control_iot_device()` in `routes/iot.py`, with a
   command→(capability, command, args) mapping mirroring
   `ha_utils.translate_generic_control_params()`'s role for HA — probably worth a symmetrical
   `st_utils.translate_generic_control_params(device_type, command, params)` for testability
   (see `tests/test_ha_utils.py` for the pattern).
3. Needs real ST device testing before calling it done — no live SmartThings account/device
   available in this environment as of 2026-08-24 (same caveat `todo_esphome.md` and
   `todo_music_spotify.md` note for their own not-yet-verified-live items).

## Related

- `todo_iot.md` — Phase 4 (SmartThings Integration) and Phase 5 (Unified IoT Layer), whose
  "unified front door" claim this todo corrects.
- `todo_iot_central_control.md` — the audit pass that found this gap while confirming
  `ControlBlade.jsx`'s media_player wiring (item 1) and auditing for stranded controls (item 3).
