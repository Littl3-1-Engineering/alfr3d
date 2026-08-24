import logging
import requests
import pymysql

from .db_pool import get_connection
from . import secrets_utils

logger = logging.getLogger("STLog")

ST_API_BASE = "https://api.smartthings.com/v1"


def get_st_config():
    db = None
    try:
        db = get_connection()
        cursor = db.cursor()
        config = {}
        cursor.execute("SELECT name, value FROM config WHERE name = 'st_pat'")
        for row in cursor.fetchall():
            config[row[0]] = row[1]
        if config.get("st_pat"):
            config["st_pat"] = secrets_utils.decrypt_or_plaintext(config["st_pat"])
        return config
    except pymysql.Error as e:
        logger.error(f"Database error fetching ST config: {e}")
        if db:
            db.rollback()
        return {}
    finally:
        if db:
            db.close()


def is_st_configured():
    config = get_st_config()
    return bool(config.get("st_pat"))


def test_st_connection():
    config = get_st_config()
    st_pat = config.get("st_pat", "")

    if not st_pat:
        return False, "PAT not configured"

    try:
        response = requests.get(
            f"{ST_API_BASE}/devices",
            headers={"Authorization": f"Bearer {st_pat}"},
            timeout=10,
        )
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.RequestException as e:
        return False, f"Request failed: {e}"
    except Exception as e:
        logger.error(f"Unexpected error testing ST connection: {e}")
        return False, str(e)


def get_st_devices():
    config = get_st_config()
    st_pat = config.get("st_pat", "")

    if not st_pat:
        return []

    try:
        response = requests.get(
            f"{ST_API_BASE}/devices",
            headers={"Authorization": f"Bearer {st_pat}"},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("items", [])
        return []
    except Exception as e:
        logger.error(f"Error fetching ST devices: {e}")
        return []


def get_st_device_status(device_id):
    config = get_st_config()
    st_pat = config.get("st_pat", "")

    if not st_pat:
        return None

    try:
        response = requests.get(
            f"{ST_API_BASE}/devices/{device_id}/status",
            headers={"Authorization": f"Bearer {st_pat}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching ST device status: {e}")
        return None


# SmartThings capability IDs (per component) -> ALFR3D's normalized device_type vocabulary --
# the same light/switch/fan/climate/cover/lock/media_player/sensor/binary_sensor domains
# ha_utils.sync_ha_devices() derives from HA's entity_id prefix and esphome_utils's
# _ENTITY_DOMAIN_MAP derives from the aioesphomeapi EntityInfo subclass. ST has no equivalent
# single field -- sync_st_devices() used to store the raw deviceTypeName/typeName label (e.g.
# "Samsung OCF Switch"), which never matched ControlBlade.jsx's renderDeviceControls() switch,
# so every ST device rendered as the generic power-toggle fallback. See
# todo/todo_smartthings_generic_control.md.
_ST_COVER_CAPS = {"windowShade", "windowShadeLevel"}
_ST_CLIMATE_CAPS = {"thermostatMode", "thermostatHeatingSetpoint", "thermostatCoolingSetpoint"}
_ST_MEDIA_PLAYER_CAPS = {"mediaPlayback", "audioVolume", "audioMute"}
_ST_LIGHT_CAPS = {"switchLevel", "colorControl", "colorTemperature"}
_ST_BINARY_SENSOR_CAPS = {"contactSensor", "motionSensor", "presenceSensor", "waterSensor"}
_ST_SENSOR_CAPS = {
    "temperatureMeasurement",
    "relativeHumidityMeasurement",
    "illuminanceMeasurement",
    "battery",
    "powerMeter",
    "energyMeter",
}

# Named fan speeds ControlBlade.jsx's speed buttons send -> ST's setFanSpeed integer levels.
# Mirrors ha_utils.translate_generic_control_params's off/low/medium/high -> percentage map,
# but ST's fanSpeed capability takes a small device-defined integer, not a 0-100 percentage.
_ST_FAN_SPEED_MAP = {"off": 0, "low": 1, "medium": 2, "high": 3}


def normalize_st_device_type(device):
    """Derive one of ControlBlade.jsx's normalized device_type strings from a SmartThings
    device's capability list, instead of storing ST's raw deviceTypeName/typeName label."""
    capability_ids = set()
    for component in device.get("components", []):
        for cap in component.get("capabilities", []):
            cap_id = cap.get("id")
            if cap_id:
                capability_ids.add(cap_id)

    if capability_ids & _ST_COVER_CAPS:
        return "cover"
    if "lock" in capability_ids:
        return "lock"
    if capability_ids & _ST_CLIMATE_CAPS:
        return "climate"
    if "fanSpeed" in capability_ids:
        return "fan"
    if capability_ids & _ST_MEDIA_PLAYER_CAPS:
        return "media_player"
    if capability_ids & _ST_LIGHT_CAPS:
        return "light"
    if "switch" in capability_ids:
        return "switch"
    if capability_ids & _ST_BINARY_SENSOR_CAPS:
        return "binary_sensor"
    if capability_ids & _ST_SENSOR_CAPS:
        return "sensor"
    return "unknown"


def translate_generic_control_params(device_type, command, params=None):
    """Map ControlBlade.jsx's provider-agnostic command vocabulary (turn_on/turn_off,
    set_brightness, set_speed, ...) onto a SmartThings (capability, command, arguments) triple --
    the shape st_control_device()/the ST REST API actually expects. Unlike HA's single service
    name + flat params dict, ST commands are capability-scoped, so the mapping also depends on
    device_type (e.g. turn_on means capability `switch` command `on` for a switch/light/fan, but
    capability `windowShade` command `open` for a cover). Returns None for a command that has no
    ST equivalent for that device_type -- callers should treat that as an unsupported command,
    the same way an unmapped HA service name would fail at HA's API instead. See
    todo/todo_smartthings_generic_control.md -- this mapping is written from the ST capability
    reference and has not been exercised against a live SmartThings device/account."""
    params = dict(params or {})

    if device_type in ("light", "switch", "fan"):
        if command == "turn_on":
            return ("switch", "on", [])
        if command == "turn_off":
            return ("switch", "off", [])
        if device_type == "light" and command == "set_brightness" and "brightness" in params:
            return ("switchLevel", "setLevel", [params["brightness"]])
        if device_type == "fan" and command == "set_speed" and "speed" in params:
            speed = _ST_FAN_SPEED_MAP.get(str(params["speed"]).lower(), 0)
            return ("fanSpeed", "setFanSpeed", [speed])
        return None

    if device_type == "climate":
        if command == "turn_on":
            return ("thermostatMode", "setThermostatMode", ["auto"])
        if command == "turn_off":
            return ("thermostatMode", "setThermostatMode", ["off"])
        if command == "set_temperature" and "temperature" in params:
            return ("thermostatHeatingSetpoint", "setHeatingSetpoint", [params["temperature"]])
        return None

    if device_type == "lock":
        if command == "lock":
            return ("lock", "lock", [])
        if command == "unlock":
            return ("lock", "unlock", [])
        return None

    if device_type == "cover":
        if command == "turn_on":
            return ("windowShade", "open", [])
        if command == "turn_off":
            return ("windowShade", "close", [])
        if command == "set_position" and "position" in params:
            return ("windowShadeLevel", "setShadeLevel", [params["position"]])
        return None

    if device_type == "media_player":
        if command == "media_play":
            return ("mediaPlayback", "play", [])
        if command == "media_pause":
            return ("mediaPlayback", "pause", [])
        if command == "volume_set" and "volume" in params:
            return ("audioVolume", "setVolume", [params["volume"]])
        return None

    return None


def st_control_device(device_id, capability, command, args=None):
    config = get_st_config()
    st_pat = config.get("st_pat", "")

    if not st_pat:
        return False, "ST not configured"

    try:
        command_body = {
            "capability": capability,
            "command": command,
        }
        if args:
            command_body["arguments"] = args

        response = requests.post(
            f"{ST_API_BASE}/devices/{device_id}/commands",
            headers={"Authorization": f"Bearer {st_pat}"},
            json={"commands": [command_body]},
            timeout=10,
        )
        if response.status_code in [200, 201]:
            return True, "Command sent"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        logger.error(f"Error controlling ST device: {e}")
        return False, str(e)


def sync_st_devices():
    if not is_st_configured():
        logger.warning("ST not configured, skipping sync")
        return False

    devices = get_st_devices()
    if not devices:
        logger.warning("No ST devices found")
        return False

    db = get_connection()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM environment ORDER BY id LIMIT 1")
    env_row = cursor.fetchone()
    env_id = env_row[0] if env_row else None

    synced = 0
    updated = 0
    linked = 0
    for device in devices:
        st_device_id = device.get("deviceId")
        label = device.get("label", device.get("name", st_device_id))
        device_type = normalize_st_device_type(device)

        device_id = None

        cursor.execute(
            "SELECT id FROM smarthome_devices WHERE source = 'smartthings' AND st_device_id = %s",
            (st_device_id,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE smarthome_devices
                SET name = %s,
                    device_type = %s,
                    online = %s,
                    device_id = COALESCE(device_id, %s)
                WHERE id = %s
                """,
                (label, device_type, True, device_id, existing[0]),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO smarthome_devices
                    (name, source, st_device_id, device_type,
                     online, environment_id, device_id)
                VALUES (%s, 'smartthings', %s, %s, %s, %s, %s)
                """,
                (label, st_device_id, device_type, True, env_id, device_id),
            )
        synced += 1

    db.commit()
    db.close()

    logger.info(f"Synced {synced} ST devices ({updated} updated), linked {linked}")
    return True


def save_st_config(st_pat):
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE config SET value = %s WHERE name = 'st_pat'",
        (secrets_utils.encrypt(st_pat),),
    )
    db.commit()
    db.close()
    return True
