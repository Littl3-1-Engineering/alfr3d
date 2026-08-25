import orjson
import logging
import requests
import pymysql

from .db_pool import get_connection
from . import secrets_utils

logger = logging.getLogger("HALog")


def get_ha_config():
    db = None
    try:
        db = get_connection()
        cursor = db.cursor()
        config = {}
        cursor.execute("SELECT name, value FROM config WHERE name IN ('ha_url', 'ha_token')")
        for row in cursor.fetchall():
            config[row[0]] = row[1]
        if config.get("ha_token"):
            config["ha_token"] = secrets_utils.decrypt_or_plaintext(config["ha_token"])
        return config
    except pymysql.Error as e:
        logger.error(f"Database error fetching HA config: {e}")
        if db:
            db.rollback()
        return {}
    finally:
        if db:
            db.close()


def is_ha_configured():
    config = get_ha_config()
    return bool(config.get("ha_url") and config.get("ha_token"))


def test_ha_connection():
    config = get_ha_config()
    ha_url = config.get("ha_url", "").rstrip("/")
    ha_token = config.get("ha_token", "")

    if not ha_url or not ha_token:
        return False, "HA URL or token not configured"

    try:
        response = requests.get(
            f"{ha_url}/api/",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.RequestException as e:
        logger.error(f"HA connection request failed: {e}")
        return False, "Request failed"
    except Exception as e:
        logger.error(f"Unexpected error testing HA connection: {e}")
        return False, "Unexpected error"


def get_ha_states():
    config = get_ha_config()
    ha_url = config.get("ha_url", "").rstrip("/")
    ha_token = config.get("ha_token", "")

    if not ha_url or not ha_token:
        return []

    try:
        response = requests.get(
            f"{ha_url}/api/states",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        return []
    except requests.RequestException as e:
        logger.error(f"Request error fetching HA states: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching HA states: {e}")
        return []


def get_ha_devices():
    states = get_ha_states()
    devices = []

    for state in states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""

        if domain in [
            "light",
            "switch",
            "fan",
            "climate",
            "cover",
            "lock",
            "media_player",
            "sensor",
            "binary_sensor",
            "camera",
        ]:
            connections = state.get("attributes", {}).get("connections", [])
            mac_address = None
            for conn_type, conn_value in connections:
                if conn_type == "mac":
                    mac_address = conn_value.upper()
                    break

            device = {
                "entity_id": entity_id,
                "name": state.get("attributes", {}).get("friendly_name", entity_id),
                "state": state.get("state"),
                "domain": domain,
                "last_changed": state.get("last_changed"),
                "attributes": state.get("attributes", {}),
                "mac_address": mac_address,
            }

            if "brightness" in state.get("attributes", {}):
                device["brightness"] = state["attributes"]["brightness"]

            devices.append(device)

    return devices


def get_ha_device_state(entity_id):
    config = get_ha_config()
    ha_url = config.get("ha_url", "").rstrip("/")
    ha_token = config.get("ha_token", "")

    if not ha_url or not ha_token:
        return None

    try:
        response = requests.get(
            f"{ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching HA device state: {e}")
        return None


def translate_generic_control_params(command, params):
    """Map ControlBlade.jsx's provider-agnostic command vocabulary (turn_on/turn_off,
    set_brightness, set_speed, volume_set, ...) onto the service-call `data` HA's actual REST
    API expects for that command. HA's bare `brightness` field is raw 0-255, `volume_level` is a
    0.0-1.0 float, and `fan.set_percentage` takes a numeric `percentage` -- none of which match
    what ControlBlade's sliders/buttons send (0-100 percents and named fan speeds), so passing
    params straight through silently sends the wrong value (or a payload HA rejects outright).
    See todo/todo_iot_central_control.md."""
    params = dict(params or {})
    if command == "set_brightness" and "brightness" in params:
        return {"brightness_pct": params["brightness"]}
    if command == "volume_set" and "volume" in params:
        return {"volume_level": params["volume"] / 100.0}
    if command == "set_speed" and "speed" in params:
        percentage = {"off": 0, "low": 33, "medium": 66, "high": 100}.get(
            str(params["speed"]).lower(), 0
        )
        return {"percentage": percentage}
    return params


def ha_control_device(entity_id, service, data=None):
    config = get_ha_config()
    ha_url = config.get("ha_url", "").rstrip("/")
    ha_token = config.get("ha_token", "")

    if not ha_url or not ha_token:
        return False, "HA not configured"

    domain = entity_id.split(".")[0] if "." in entity_id else None
    if not domain:
        return False, "Invalid entity_id"

    try:
        service_data = {"entity_id": entity_id}
        if data:
            service_data.update(data)

        response = requests.post(
            f"{ha_url}/api/services/{domain}/{service}",
            headers={"Authorization": f"Bearer {ha_token}"},
            json=service_data,
            timeout=10,
        )
        if response.status_code in [200, 201]:
            return True, "Command sent"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        logger.error(f"Error controlling HA device: {e}")
        return False, "Failed to control device"


def sync_ha_devices():
    if not is_ha_configured():
        logger.warning("HA not configured, skipping sync")
        return False

    devices = get_ha_devices()
    if not devices:
        logger.warning("No HA devices found")
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
        entity_id = device["entity_id"]
        name = device["name"]
        device_type = device["domain"]
        state = device["state"]
        mac_address = device.get("mac_address")

        device_id = None

        if mac_address:
            cursor.execute(
                "SELECT id FROM device WHERE UPPER(MAC) = %s",
                (mac_address.upper(),),
            )
            row = cursor.fetchone()
            if row:
                device_id = row[0]
                linked += 1

        last_state = orjson.dumps(device).decode("utf-8")
        online = state == "on"

        cursor.execute(
            "SELECT id FROM smarthome_devices WHERE source = 'homeassistant' AND ha_entity_id = %s",
            (entity_id,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE smarthome_devices
                SET name = %s,
                    mac_address = COALESCE(%s, mac_address),
                    device_type = %s,
                    online = %s,
                    last_state = %s,
                    device_id = COALESCE(device_id, %s)
                WHERE id = %s
                """,
                (name, mac_address, device_type, online, last_state, device_id, existing[0]),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO smarthome_devices
                    (name, source, ha_entity_id, mac_address, device_type, online,
                     last_state, environment_id, device_id)
                VALUES (%s, 'homeassistant', %s, %s, %s, %s, %s, %s, %s)
                """,
                (name, entity_id, mac_address, device_type, online, last_state, env_id, device_id),
            )
        synced += 1

    db.commit()
    db.close()

    logger.info(f"Synced {synced} HA devices ({updated} updated), linked {linked}")
    return True


def save_ha_config(ha_url, ha_token):
    db = get_connection()
    cursor = db.cursor()

    cursor.execute("UPDATE config SET value = %s WHERE name = 'ha_url'", (ha_url,))
    cursor.execute(
        "UPDATE config SET value = %s WHERE name = 'ha_token'",
        (secrets_utils.encrypt(ha_token),),
    )

    db.commit()
    db.close()

    return True
