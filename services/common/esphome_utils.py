"""ESPHome integration: mDNS discovery + native API client (Noise-encrypted, port 6053 default).

Not registered in `common/__init__.py`'s eager import list (unlike ha_utils/st_utils) --
aioesphomeapi/zeroconf are heavier, newer dependencies than the rest of this package's imports,
and every service that does `from common import X` triggers `common/__init__.py` in full. Callers
use `from common import esphome_utils` directly; Python's import system resolves that as a
submodule import even without an `__init__.py` entry. See todo/todo_esphome.md Design section 2.

Unlike ha_utils.py/st_utils.py, this module is not purely synchronous: aioesphomeapi is
asyncio-only. Functions ending in `_async` are the core implementation and are meant to be
`await`-ed directly from service_api's FastAPI routes (already inside a running event loop).
Functions without that suffix are synchronous, safe to call from service_device's blocking Kafka
consumer loop the same way ha_utils/st_utils functions are; internally they wrap the async core
with `asyncio.run()`. Discovery itself uses zeroconf's sync API and needs no event loop at all.
"""

import asyncio
import logging
import time

import orjson
import pymysql
from aioesphomeapi import APIClient, FanSpeed, LockCommand, MediaPlayerCommand
from zeroconf import ServiceBrowser, Zeroconf

from .db_pool import get_connection
from . import secrets_utils

logger = logging.getLogger("ESPHomeLog")

ESPHOME_SERVICE_TYPE = "_esphomelib._tcp.local."
DEFAULT_PORT = 6053

# aioesphomeapi EntityInfo subclass name -> ALFR3D device_type. Matches the domain list
# ha_utils.get_ha_devices() already filters to (migration_007_device_types_expansion.sql).
_ENTITY_DOMAIN_MAP = {
    "SwitchInfo": "switch",
    "LightInfo": "light",
    "FanInfo": "fan",
    "ClimateInfo": "climate",
    "CoverInfo": "cover",
    "LockInfo": "lock",
    "MediaPlayerInfo": "media_player",
    "SensorInfo": "sensor",
    "BinarySensorInfo": "binary_sensor",
    "CameraInfo": "camera",
}


# --- Config -------------------------------------------------------------------------------


def get_esphome_config():
    db = None
    try:
        db = get_connection()
        cursor = db.cursor()
        config = {}
        cursor.execute("SELECT name, value FROM config WHERE name = 'esphome_enabled'")
        for row in cursor.fetchall():
            config[row[0]] = row[1]
        return config
    except pymysql.Error as e:
        logger.error(f"Database error fetching ESPHome config: {e}")
        if db:
            db.rollback()
        return {}
    finally:
        if db:
            db.close()


def is_esphome_enabled():
    config = get_esphome_config()
    return config.get("esphome_enabled", "true") == "true"


def save_esphome_enabled(enabled):
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE config SET value = %s WHERE name = 'esphome_enabled'",
        ("true" if enabled else "false",),
    )
    db.commit()
    db.close()
    return True


# --- Discovery (sync, zeroconf) ------------------------------------------------------------


class _DiscoveryListener:
    def __init__(self):
        self.found = {}

    def add_service(self, zc, service_type, name):
        self._update(zc, service_type, name)

    def update_service(self, zc, service_type, name):
        self._update(zc, service_type, name)

    def remove_service(self, zc, service_type, name):
        pass

    def _update(self, zc, service_type, name):
        info = zc.get_service_info(service_type, name)
        if info is None:
            return
        addresses = info.parsed_addresses()
        if not addresses:
            return
        hostname = (info.server or name).rstrip(".")
        self.found[hostname] = {
            "hostname": hostname,
            "ip_address": addresses[0],
            "port": info.port or DEFAULT_PORT,
            "name": name.split(f".{service_type}")[0],
        }


def discover_esphome_nodes(timeout=8):
    """Blocking mDNS scan for ESPHome nodes on the LAN. Upserts esphome_nodes rows but never
    sets accepted=TRUE itself -- see migration_019_esphome.sql's comment and
    todo/todo_esphome.md Design section 1 (mDNS discovery isn't account-scoped like HA/ST, so
    nodes must not auto-link)."""
    listener = _DiscoveryListener()
    zc = Zeroconf()
    try:
        ServiceBrowser(zc, ESPHOME_SERVICE_TYPE, listener)
        time.sleep(timeout)
    finally:
        zc.close()

    nodes = list(listener.found.values())
    if not nodes:
        return []

    db = get_connection()
    cursor = db.cursor()
    for node in nodes:
        cursor.execute(
            """
            INSERT INTO esphome_nodes (hostname, ip_address, port, name)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                ip_address = VALUES(ip_address),
                port = VALUES(port),
                name = COALESCE(name, VALUES(name)),
                last_seen = CURRENT_TIMESTAMP
            """,
            (node["hostname"], node["ip_address"], node["port"], node["name"]),
        )
    db.commit()
    db.close()

    logger.info(f"ESPHome discovery found {len(nodes)} node(s)")
    return nodes


def get_esphome_nodes(accepted=None):
    db = get_connection()
    cursor = db.cursor()
    if accepted is None:
        cursor.execute(
            "SELECT id, hostname, ip_address, port, name, accepted, last_seen "
            "FROM esphome_nodes ORDER BY hostname"
        )
    else:
        cursor.execute(
            "SELECT id, hostname, ip_address, port, name, accepted, last_seen "
            "FROM esphome_nodes WHERE accepted = %s ORDER BY hostname",
            (accepted,),
        )
    rows = cursor.fetchall()
    db.close()
    return [
        {
            "id": r[0],
            "hostname": r[1],
            "ip_address": r[2],
            "port": r[3],
            "name": r[4],
            "accepted": bool(r[5]),
            "last_seen": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def remove_esphome_node(hostname):
    """Removes a node entirely: its esphome_nodes row and any synced entities. Discovery will
    re-surface it (as unaccepted) if it's still broadcasting on the LAN."""
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM smarthome_devices WHERE source = 'esphome' AND esp_entity_id LIKE %s",
        (f"{hostname}:%",),
    )
    cursor.execute("DELETE FROM esphome_nodes WHERE hostname = %s", (hostname,))
    db.commit()
    db.close()
    return True


# --- Client (async core) -------------------------------------------------------------------


async def _fetch_node_snapshot(host, port, psk, connect_timeout=10, state_settle=2):
    """Connect, fetch device info + entity list, and collect the initial state push burst.

    NOTE: sleeping `state_settle` seconds to catch pushed states is a pragmatic v1 shortcut --
    a persistent connection (todo/todo_esphome.md Design section 2, Phase B) would remove the
    need for this by keeping states current via subscribe_states() continuously instead of a
    connect/snapshot/disconnect cycle every sync."""
    client = APIClient(host, port, password=None, noise_psk=psk or None)
    states = {}

    def on_state(state):
        states[state.key] = state

    await asyncio.wait_for(client.connect(login=True), timeout=connect_timeout)
    try:
        device_info = await client.device_info()
        entities, _services = await client.list_entities_services()
        client.subscribe_states(on_state)
        await asyncio.sleep(state_settle)
        return device_info, entities, states
    finally:
        await client.disconnect()


async def test_esphome_node_async(host, port, psk):
    try:
        device_info, entities, _states = await _fetch_node_snapshot(host, port, psk)
        return True, f"Connected ({len(entities)} entities)", device_info, entities
    except Exception as e:
        logger.error(f"Error connecting to ESPHome node {host}: {e}")
        return False, str(e), None, []


async def accept_esphome_node_async(hostname, psk=None, name=None):
    """Validate connectivity to a discovered node, then mark it accepted and do an initial
    entity sync. Returns (success, message, device_info)."""
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "SELECT ip_address, port FROM esphome_nodes WHERE hostname = %s",
        (hostname,),
    )
    row = cursor.fetchone()
    db.close()
    if not row:
        return False, "Node not found -- run discovery first", None

    ip_address, port = row
    host = ip_address or hostname

    success, message, device_info, entities = await test_esphome_node_async(host, port, psk)
    if not success:
        return False, message, None

    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        """
        UPDATE esphome_nodes
        SET accepted = TRUE, psk = %s, name = COALESCE(%s, name), accepted_at = CURRENT_TIMESTAMP
        WHERE hostname = %s
        """,
        (secrets_utils.encrypt(psk) if psk else psk, name, hostname),
    )
    db.commit()
    db.close()

    _upsert_node_entities(hostname, device_info, entities, {})
    return True, message, device_info


def _fan_speed_command(params):
    speed = str(params.get("speed", "")).lower()
    if speed in ("off", ""):
        return {"state": False}
    if speed in ("low", "medium", "high"):
        return {"state": True, "speed": FanSpeed[speed.upper()]}
    return {"state": True}


async def control_esphome_device_async(hostname, key, domain, command, params=None):
    """Send a control command to one entity. `domain`/`key` come from the smarthome_devices row
    (device_type, esp_entity_id's ':key' suffix) -- see routes/iot.py's unified control endpoint.
    Command vocabulary matches what ControlBlade.jsx already sends for HA/ST (turn_on/turn_off,
    set_brightness, lock/unlock, set_speed, set_position, set_temperature, media_play/pause,
    volume_set) -- no ESPHome-specific command names."""
    params = params or {}
    db = get_connection()
    cursor = db.cursor()
    cursor.execute(
        "SELECT ip_address, port, psk FROM esphome_nodes WHERE hostname = %s AND accepted = TRUE",
        (hostname,),
    )
    row = cursor.fetchone()
    db.close()
    if not row:
        return False, "Node not found or not accepted"

    ip_address, port, psk = row
    psk = secrets_utils.decrypt_or_plaintext(psk) if psk else psk
    host = ip_address or hostname
    client = APIClient(host, port, password=None, noise_psk=psk or None)

    try:
        await asyncio.wait_for(client.connect(login=True), timeout=10)

        if domain in ("switch", "light", "fan") and command in ("turn_on", "turn_off"):
            state = command == "turn_on"
            if domain == "switch":
                client.switch_command(key=key, state=state)
            elif domain == "light":
                client.light_command(key=key, state=state)
            else:
                client.fan_command(key=key, state=state)
        elif domain == "light" and command == "set_brightness":
            brightness = float(params.get("brightness", 255)) / 255
            client.light_command(key=key, state=True, brightness=brightness)
        elif domain == "lock" and command in ("lock", "unlock"):
            client.lock_command(
                key=key, command=LockCommand.LOCK if command == "lock" else LockCommand.UNLOCK
            )
        elif domain == "fan" and command == "set_speed":
            client.fan_command(key=key, **_fan_speed_command(params))
        elif domain == "cover" and command == "set_position":
            client.cover_command(key=key, position=float(params.get("position", 0)) / 100)
        elif domain == "climate" and command == "set_temperature":
            client.climate_command(key=key, target_temperature=float(params["temperature"]))
        elif domain == "media_player" and command in ("media_play", "media_pause"):
            mp_command = (
                MediaPlayerCommand.PLAY if command == "media_play" else MediaPlayerCommand.PAUSE
            )
            client.media_player_command(key=key, command=mp_command)
        elif domain == "media_player" and command == "volume_set":
            client.media_player_command(key=key, volume=float(params.get("volume", 0)))
        else:
            return False, f"Unsupported command '{command}' for domain '{domain}'"

        return True, "Command sent"
    except Exception as e:
        logger.error(f"Error controlling ESPHome entity {hostname}:{key}: {e}")
        return False, str(e)
    finally:
        await client.disconnect()


# --- Sync (periodic, upserts into smarthome_devices) ----------------------------------------


def _upsert_node_entities(hostname, device_info, entities, states):
    """Shared by accept_esphome_node_async (initial sync of one node) and
    sync_esphome_devices_async (periodic sync of all accepted nodes). Mirrors
    ha_utils.sync_ha_devices()'s per-entity upsert + MAC-based device linking."""
    db = get_connection()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM environment ORDER BY id LIMIT 1")
    env_row = cursor.fetchone()
    env_id = env_row[0] if env_row else None

    device_id = None
    mac_address = (device_info.mac_address or "").upper() if device_info else None
    if mac_address:
        cursor.execute("SELECT id FROM device WHERE UPPER(MAC) = %s", (mac_address,))
        row = cursor.fetchone()
        if row:
            device_id = row[0]

    synced = 0
    for entity in entities:
        domain = _ENTITY_DOMAIN_MAP.get(type(entity).__name__)
        if domain is None:
            continue

        esp_entity_id = f"{hostname}:{entity.key}"
        name = entity.name or entity.object_id or esp_entity_id
        state = states.get(entity.key)
        online = state is not None
        last_state = orjson.dumps(
            {
                "object_id": entity.object_id,
                "key": entity.key,
                "state": state.to_dict() if state else None,
            }
        ).decode("utf-8")

        cursor.execute(
            "SELECT id FROM smarthome_devices WHERE source = 'esphome' AND esp_entity_id = %s",
            (esp_entity_id,),
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
                (name, mac_address, domain, online, last_state, device_id, existing[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO smarthome_devices
                    (name, source, esp_entity_id, mac_address, device_type, online,
                     last_state, environment_id, device_id)
                VALUES (%s, 'esphome', %s, %s, %s, %s, %s, %s, %s)
                """,
                (name, esp_entity_id, mac_address, domain, online, last_state, env_id, device_id),
            )
        synced += 1

    db.commit()
    db.close()
    logger.info(f"Synced {synced} entities from ESPHome node {hostname}")
    return synced


async def sync_esphome_devices_async():
    if not is_esphome_enabled():
        logger.warning("ESPHome disabled, skipping sync")
        return False

    nodes = get_esphome_nodes(accepted=True)
    if not nodes:
        logger.info("No accepted ESPHome nodes, skipping sync")
        return False

    total = 0
    for node in nodes:
        host = node["ip_address"] or node["hostname"]
        try:
            db = get_connection()
            cursor = db.cursor()
            cursor.execute("SELECT psk FROM esphome_nodes WHERE hostname = %s", (node["hostname"],))
            psk_row = cursor.fetchone()
            db.close()
            psk = psk_row[0] if psk_row else None
            psk = secrets_utils.decrypt_or_plaintext(psk) if psk else psk

            device_info, entities, states = await _fetch_node_snapshot(host, node["port"], psk)
            total += _upsert_node_entities(node["hostname"], device_info, entities, states)
        except Exception as e:
            logger.error(f"Error syncing ESPHome node {node['hostname']}: {e}")

    return total > 0


def sync_esphome_devices():
    """Sync wrapper for service_device's blocking Kafka consumer loop -- mirrors
    ha_utils.sync_ha_devices()'s call shape (see service_device/app.py's action dispatch)."""
    return asyncio.run(sync_esphome_devices_async())
