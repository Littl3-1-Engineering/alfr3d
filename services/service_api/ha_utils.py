import os
import json
import logging
import requests
import pymysql

logger = logging.getLogger("HALog")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "rootpassword")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

if MYSQL_HOST == "mysql":
    MYSQL_HOST = "mysql"


def get_ha_config():
    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()
    config = {}
    cursor.execute("SELECT name, value FROM config WHERE name IN ('ha_url', 'ha_token')")
    for row in cursor.fetchall():
        config[row[0]] = row[1]
    db.close()
    return config


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
            f"{ha_url}/api/", headers={"Authorization": f"Bearer {ha_token}"}, timeout=10
        )
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)


def get_ha_states():
    config = get_ha_config()
    ha_url = config.get("ha_url", "").rstrip("/")
    ha_token = config.get("ha_token", "")

    if not ha_url or not ha_token:
        return []

    try:
        response = requests.get(
            f"{ha_url}/api/states", headers={"Authorization": f"Bearer {ha_token}"}, timeout=30
        )
        if response.status_code == 200:
            return response.json()
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

        if domain in ["light", "switch", "fan", "climate", "cover", "lock", "media_player"]:
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
        return False, str(e)


def sync_ha_devices():
    if not is_ha_configured():
        logger.warning("HA not configured, skipping sync")
        return False

    devices = get_ha_devices()
    if not devices:
        logger.warning("No HA devices found")
        return False

    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()

    cursor.execute("SELECT id FROM environment ORDER BY id LIMIT 1")
    env_row = cursor.fetchone()
    env_id = env_row[0] if env_row else None

    synced = 0
    for device in devices:
        entity_id = device["entity_id"]
        name = device["name"]
        device_type = device["domain"]
        state = device["state"]
        mac_address = device.get("mac_address")

        cursor.execute(
            """
            INSERT INTO smarthome_devices
                (name, source, ha_entity_id, mac_address, device_type, online,
                 last_state, environment_id)
            VALUES (%s, 'homeassistant', %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                mac_address = COALESCE(VALUES(mac_address), mac_address),
                device_type = VALUES(device_type),
                online = VALUES(online),
                last_state = VALUES(last_state)
        """,
            (name, entity_id, mac_address, device_type, state == "on", json.dumps(device), env_id),
        )
        synced += 1

    db.commit()
    db.close()

    logger.info(f"Synced {synced} HA devices")
    return True


def save_ha_config(ha_url, ha_token):
    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()

    cursor.execute("UPDATE config SET value = %s WHERE name = 'ha_url'", (ha_url,))
    cursor.execute("UPDATE config SET value = %s WHERE name = 'ha_token'", (ha_token,))

    db.commit()
    db.close()

    return True
