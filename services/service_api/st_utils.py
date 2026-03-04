import os
import logging
import requests
import pymysql

logger = logging.getLogger("STLog")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "rootpassword")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

if MYSQL_HOST == "mysql":
    MYSQL_HOST = "mysql"

ST_API_BASE = "https://api.smartthings.com/v1"


def get_st_config():
    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()
    config = {}
    cursor.execute("SELECT name, value FROM config WHERE name = 'st_pat'")
    for row in cursor.fetchall():
        config[row[0]] = row[1]
    db.close()
    return config


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
            f"{ST_API_BASE}/devices", headers={"Authorization": f"Bearer {st_pat}"}, timeout=10
        )
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)


def get_st_devices():
    config = get_st_config()
    st_pat = config.get("st_pat", "")

    if not st_pat:
        return []

    try:
        response = requests.get(
            f"{ST_API_BASE}/devices", headers={"Authorization": f"Bearer {st_pat}"}, timeout=30
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

    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()

    cursor.execute("SELECT id FROM environment ORDER BY id LIMIT 1")
    env_row = cursor.fetchone()
    env_id = env_row[0] if env_row else None

    synced = 0
    for device in devices:
        device_id = device.get("deviceId")
        label = device.get("label", device.get("name", device_id))
        device_type = device.get("deviceTypeName", device.get("typeName", "unknown"))

        cursor.execute(
            """
            INSERT INTO smarthome_devices
                (name, source, st_device_id, device_type,
                 online, environment_id)
            VALUES (%s, 'smartthings', %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                device_type = VALUES(device_type),
                online = VALUES(online)
        """,
            (label, device_id, device_type, True, env_id),
        )
        synced += 1

    db.commit()
    db.close()

    logger.info(f"Synced {synced} ST devices")
    return True


def save_st_config(st_pat):
    db = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()
    cursor.execute("UPDATE config SET value = %s WHERE name = 'st_pat'", (st_pat,))
    db.commit()
    db.close()
    return True
