import os
import logging
import requests
import pymysql

from .db_pool import get_connection

logger = logging.getLogger("STLog")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "rootpassword")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

if MYSQL_HOST == "mysql":
    MYSQL_HOST = "mysql"

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
    linked = 0
    created = 0
    for device in devices:
        st_device_id = device.get("deviceId")
        label = device.get("label", device.get("name", st_device_id))
        device_type = device.get("deviceTypeName", device.get("typeName", "unknown"))

        mac_address = None
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
            else:
                cursor.execute(
                    """
                    SELECT s.id as state_id, dt.id as type_id,
                           u.id as user_id, e.id as env_id
                    FROM states s, device_types dt, user u, environment e
                    WHERE s.state = 'online' AND dt.type = 'guest'
                    AND u.username = 'alfr3d' AND e.name = 'Home'
                    """,
                )
                result = cursor.fetchone()
                if result:
                    devstate, devtype, usrid, envid = result
                    cursor.execute(
                        "INSERT INTO device(name, IP, MAC, last_online, state, "
                        "device_type, user_id, environment_id) "
                        "VALUES (%s, '0.0.0.0', %s, NOW(), %s, %s, %s, %s)",
                        (
                            label,
                            mac_address,
                            devstate,
                            devtype,
                            usrid,
                            envid,
                        ),
                    )
                    device_id = cursor.lastrowid
                    created += 1

        cursor.execute(
            """
            INSERT INTO smarthome_devices
                (name, source, st_device_id, device_type,
                 online, environment_id, device_id)
            VALUES (%s, 'smartthings', %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                device_type = VALUES(device_type),
                online = VALUES(online),
                device_id = COALESCE(device_id, VALUES(device_id))
        """,
            (label, st_device_id, device_type, True, env_id, device_id),
        )
        synced += 1

    db.commit()
    db.close()

    logger.info(f"Synced {synced} ST devices, linked {linked}, created {created} device records")
    return True


def save_st_config(st_pat):
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE config SET value = %s WHERE name = 'st_pat'", (st_pat,))
    db.commit()
    db.close()
    return True
