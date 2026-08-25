"""IoT integration routes (Home Assistant + SmartThings + ESPHome)."""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
import orjson
import pymysql

from dependencies import db_connection, get_producer, manager
from models import (
    HAControl,
    HAConfig,
    STControl,
    STConfig,
    IoTProvider,
    LinkDevice,
    IOTDeviceControl,
    ESPHomeAccept,
    ESPHomeControl,
    ESPHomeConfig,
)
from auth.dependencies import require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["iot"])


def fetch_iot_devices_data(linked_only=False):
    """Returns devices from every configured/synced source (HA, SmartThings, ESPHome) --
    not filtered by the `iot_provider` config value. That value now only selects the *default*
    provider for actions that need a single one (see set_iot_provider below); it used to also
    gate which sources this endpoint returned at all, which meant HA and SmartThings could never
    both appear, and would have hidden ESPHome devices entirely. ESPHome runs as an always-on
    parallel source by design -- see todo/todo_esphome.md Design section 5."""
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT sd.id, sd.name, sd.source, sd.ha_entity_id, sd.st_device_id,
                       sd.esp_entity_id, sd.device_type, sd.room, sd.capabilities, sd.online,
                       sd.last_state, sd.mac_address, sd.device_id as linked_device_id,
                       d.IP, d.position_x, d.position_y, dt.type as linked_device_type
                FROM smarthome_devices sd
                JOIN (
                    SELECT MAX(id) AS id
                    FROM smarthome_devices
                    GROUP BY source, COALESCE(ha_entity_id, st_device_id, esp_entity_id)
                ) latest ON latest.id = sd.id
                LEFT JOIN device d ON sd.device_id = d.id
                LEFT JOIN device_types dt ON d.device_type = dt.id
                WHERE (%s = FALSE OR sd.device_id IS NOT NULL)
            """,
                (1 if linked_only else 0,),
            )

            devices = []
            for row in cursor.fetchall():
                linked_device_id = row[12]
                devices.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "source": row[2],
                        "ha_entity_id": row[3],
                        "st_device_id": row[4],
                        "esp_entity_id": row[5],
                        "device_type": row[6],
                        "room": row[7],
                        "capabilities": orjson.loads(row[8]) if row[8] else [],
                        "online": bool(row[9]),
                        "last_state": orjson.loads(row[10]) if row[10] else {},
                        "mac_address": row[11],
                        "linked": linked_device_id is not None,
                        "local_device": (
                            {
                                "id": linked_device_id,
                                "IP": row[13],
                                "position_x": row[14],
                                "position_y": row[15],
                                "device_type": row[16],
                            }
                            if linked_device_id
                            else None
                        ),
                    }
                )
            return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching IoT devices data: {str(e)}")
        return []


async def broadcast_iot_devices():
    while True:
        try:
            devices = await asyncio.get_event_loop().run_in_executor(None, fetch_iot_devices_data)
            await manager.broadcast("iot_devices", devices)
        except Exception as e:
            logger.error(f"Error broadcasting IoT devices: {str(e)}")
        await asyncio.sleep(30)


# --- Home Assistant ---


@router.get("/iot/ha/status")
async def get_ha_status():
    try:
        from common import ha_utils

        connected, message = ha_utils.test_ha_connection()
        return {"connected": connected, "message": message}
    except Exception as e:
        logger.error(f"Error checking HA status: {str(e)}")
        return {"connected": False, "error": "Failed to check status"}


@router.get("/iot/ha/devices")
async def get_ha_devices():
    try:
        from common import ha_utils

        devices = ha_utils.get_ha_devices()
        return devices
    except Exception as e:
        logger.error(f"Error fetching HA devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/ha/devices/{entity_id}/control")
async def control_ha_device(
    entity_id: str, data: HAControl, _perm=Depends(require_permission("iot", "control"))
):
    service_map = {
        "turn_on": "turn_on",
        "turn_off": "turn_off",
        "toggle": "toggle",
        "set_brightness": "turn_on",
    }
    service = service_map.get(data.command, data.command)

    try:
        from common import ha_utils

        success, message = ha_utils.ha_control_device(entity_id, service, data.params)
        if success:
            return {"message": message, "entity_id": entity_id, "command": data.command}
        else:
            raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        logger.error(f"Error controlling HA device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/iot/ha/config")
async def save_ha_config(data: HAConfig, _perm=Depends(require_permission("iot", "ha_config"))):
    try:
        from common import ha_utils

        ha_utils.save_ha_config(data.ha_url, data.ha_token)
        return {"message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving HA config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/ha/sync")
async def trigger_ha_sync(_perm=Depends(require_permission("iot", "ha_sync"))):
    try:
        producer = get_producer()
        if producer:
            producer.send("device", {"action": "iot_ha_sync"})
            producer.flush()
            logger.info("HA sync triggered")
            return {"message": "Sync triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Kafka")
    except Exception as e:
        logger.error(f"Error triggering HA sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# --- SmartThings ---


@router.get("/iot/st/status")
async def get_st_status():
    try:
        from common import st_utils

        connected, message = st_utils.test_st_connection()
        return {"connected": connected, "message": message}
    except Exception as e:
        logger.error(f"Error checking ST status: {str(e)}")
        return {"connected": False, "error": "Failed to check status"}


@router.get("/iot/st/devices")
async def get_st_devices():
    try:
        from common import st_utils

        devices = st_utils.get_st_devices()
        return devices
    except Exception as e:
        logger.error(f"Error fetching ST devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/st/devices/{device_id}/control")
async def control_st_device(
    device_id: str, data: STControl, _perm=Depends(require_permission("iot", "control"))
):
    try:
        from common import st_utils

        success, message = st_utils.st_control_device(
            device_id, data.capability, data.command, data.args
        )
        if success:
            return {"message": message, "device_id": device_id, "command": data.command}
        else:
            raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        logger.error(f"Error controlling ST device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/iot/st/config")
async def save_st_config(data: STConfig, _perm=Depends(require_permission("iot", "st_config"))):
    try:
        from common import st_utils

        st_utils.save_st_config(data.st_pat)
        return {"message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving ST config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/st/sync")
async def trigger_st_sync(_perm=Depends(require_permission("iot", "st_sync"))):
    try:
        producer = get_producer()
        if producer:
            producer.send("device", {"action": "iot_st_sync"})
            producer.flush()
            logger.info("ST sync triggered")
            return {"message": "Sync triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Kafka")
    except Exception as e:
        logger.error(f"Error triggering ST sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# --- ESPHome ---
# Unlike HA/ST, ESPHome has no single URL/token to configure -- each node is discovered over
# mDNS and accepted individually (see todo/todo_esphome.md Design section 1 for why discovered
# nodes require an explicit accept step rather than auto-linking like HA/ST sync does).


@router.get("/iot/esphome/status")
async def get_esphome_status():
    try:
        from common import esphome_utils

        enabled = esphome_utils.is_esphome_enabled()
        accepted = esphome_utils.get_esphome_nodes(accepted=True)
        return {"enabled": enabled, "accepted_nodes": len(accepted), "nodes": accepted}
    except Exception as e:
        logger.error(f"Error checking ESPHome status: {str(e)}")
        return {"enabled": False, "error": "Failed to check status"}


@router.put("/iot/esphome/config")
async def save_esphome_config(
    data: ESPHomeConfig, _perm=Depends(require_permission("iot", "esphome_config"))
):
    try:
        from common import esphome_utils

        esphome_utils.save_esphome_enabled(data.enabled)
        return {"message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving ESPHome config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iot/esphome/nodes")
async def get_esphome_nodes(accepted: bool | None = None):
    try:
        from common import esphome_utils

        return esphome_utils.get_esphome_nodes(accepted=accepted)
    except Exception as e:
        logger.error(f"Error fetching ESPHome nodes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/esphome/discover")
async def trigger_esphome_discovery(
    _perm=Depends(require_permission("iot", "esphome_discover")),
):
    """Runs a blocking ~8s mDNS scan, so it's offloaded to a worker thread rather than run
    directly in this coroutine (unlike HA/ST's sub-second calls, this would otherwise stall
    every other request being served by this event loop for the scan's duration)."""
    try:
        from common import esphome_utils

        nodes = await asyncio.get_event_loop().run_in_executor(
            None, esphome_utils.discover_esphome_nodes
        )
        return {"message": f"Discovery found {len(nodes)} node(s)", "nodes": nodes}
    except Exception as e:
        logger.error(f"Error running ESPHome discovery: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/esphome/nodes/{hostname}/accept")
async def accept_esphome_node(
    hostname: str,
    data: ESPHomeAccept,
    _perm=Depends(require_permission("iot", "esphome_accept")),
):
    try:
        from common import esphome_utils

        success, message, _device_info = await esphome_utils.accept_esphome_node_async(
            hostname, psk=data.psk, name=data.name
        )
        if not success:
            raise HTTPException(status_code=500, detail=message)

        devices = await asyncio.get_event_loop().run_in_executor(None, fetch_iot_devices_data)
        await manager.broadcast("iot_devices", devices)
        return {"message": message, "hostname": hostname}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting ESPHome node {hostname}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/iot/esphome/nodes/{hostname}")
async def remove_esphome_node(
    hostname: str, _perm=Depends(require_permission("iot", "esphome_remove"))
):
    try:
        from common import esphome_utils

        esphome_utils.remove_esphome_node(hostname)
        devices = await asyncio.get_event_loop().run_in_executor(None, fetch_iot_devices_data)
        await manager.broadcast("iot_devices", devices)
        return {"message": "Node removed", "hostname": hostname}
    except Exception as e:
        logger.error(f"Error removing ESPHome node {hostname}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/esphome/entities/{hostname}/{key}/control")
async def control_esphome_entity(
    hostname: str,
    key: int,
    data: ESPHomeControl,
    _perm=Depends(require_permission("iot", "control")),
):
    try:
        from common import esphome_utils

        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT device_type FROM smarthome_devices WHERE source = 'esphome' "
                "AND esp_entity_id = %s",
                (f"{hostname}:{key}",),
            )
            row = cursor.fetchone()
        domain = row[0] if row else None
        if not domain:
            raise HTTPException(status_code=404, detail="Entity not found")

        success, message = await esphome_utils.control_esphome_device_async(
            hostname, key, domain, data.command, data.params
        )
        if not success:
            raise HTTPException(status_code=500, detail=message)

        devices = await asyncio.get_event_loop().run_in_executor(None, fetch_iot_devices_data)
        await manager.broadcast("iot_devices", devices)
        return {"message": message, "hostname": hostname, "key": key, "command": data.command}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error controlling ESPHome entity {hostname}:{key}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/esphome/sync")
async def trigger_esphome_sync(_perm=Depends(require_permission("iot", "esphome_sync"))):
    try:
        producer = get_producer()
        if producer:
            producer.send("device", {"action": "iot_esphome_sync"})
            producer.flush()
            logger.info("ESPHome sync triggered")
            return {"message": "Sync triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Kafka")
    except Exception as e:
        logger.error(f"Error triggering ESPHome sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Unified IoT ---


@router.get("/iot/status")
async def get_iot_status():
    try:
        from common import ha_utils, st_utils, esphome_utils

        ha_connected, ha_message = ha_utils.test_ha_connection()
        st_connected, st_message = st_utils.test_st_connection()
        esphome_enabled = esphome_utils.is_esphome_enabled()
        esphome_nodes = esphome_utils.get_esphome_nodes(accepted=True)
        esphome_message = (
            f"{len(esphome_nodes)} node(s) accepted" if esphome_enabled else "Disabled"
        )
        return {
            "ha": {"connected": ha_connected, "message": ha_message},
            "st": {"connected": st_connected, "message": st_message},
            "esphome": {
                "connected": esphome_enabled and len(esphome_nodes) > 0,
                "message": esphome_message,
            },
        }
    except Exception as e:
        logger.error(f"Error checking IoT status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check IoT status")


@router.get("/iot/devices")
async def get_iot_devices(linked: bool = False):
    try:
        devices = await asyncio.get_event_loop().run_in_executor(
            None, fetch_iot_devices_data, linked
        )
        return devices
    except Exception as e:
        logger.error(f"Error fetching IoT devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/iot/devices/{device_id}/control")
async def control_iot_device(
    device_id: int, data: IOTDeviceControl, _perm=Depends(require_permission("iot", "control"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT source, ha_entity_id, device_type, esp_entity_id, st_device_id "
                "FROM smarthome_devices WHERE id = %s",
                (device_id,),
            )
            row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Device not found")

        source, ha_entity_id, device_type, esp_entity_id, st_device_id = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
        )
        command = data.command

        if source == "homeassistant" and ha_entity_id:
            from common import ha_utils

            domain = ha_entity_id.split(".")[0] if "." in ha_entity_id else "switch"

            if command == "turn_on":
                service = (
                    "turn_on"
                    if domain in ["light", "switch", "fan"]
                    else domain.split(".")[0] if "." in ha_entity_id else domain
                )
            elif command == "turn_off":
                service = "turn_off"
            elif command == "toggle":
                service = "toggle"
            elif command == "set_brightness":
                service = "turn_on"
            elif command == "set_temperature":
                service = "set_temperature"
            elif command == "set_mode":
                service = "set_mode"
            elif command == "lock":
                service = "lock"
            elif command == "unlock":
                service = "unlock"
            elif command == "set_speed":
                service = "set_percentage"
            elif command == "set_position":
                service = "set_cover_position"
            elif command == "media_play":
                service = "media_play"
            elif command == "media_pause":
                service = "media_pause"
            elif command == "volume_set":
                service = "volume_set"
            else:
                service = command

            params = ha_utils.translate_generic_control_params(command, data.params)
            success, message = ha_utils.ha_control_device(ha_entity_id, service, params)
            if success:
                devices = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_iot_devices_data
                )
                await manager.broadcast("iot_devices", devices)
                return {
                    "message": message,
                    "device_id": device_id,
                    "command": command,
                    "device_type": device_type,
                }
            else:
                raise HTTPException(status_code=500, detail=message)
        elif source == "esphome" and esp_entity_id:
            from common import esphome_utils

            hostname, _, key = esp_entity_id.rpartition(":")
            success, message = await esphome_utils.control_esphome_device_async(
                hostname, int(key), device_type, command, data.params or {}
            )
            if success:
                devices = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_iot_devices_data
                )
                await manager.broadcast("iot_devices", devices)
                return {
                    "message": message,
                    "device_id": device_id,
                    "command": command,
                    "device_type": device_type,
                }
            else:
                raise HTTPException(status_code=500, detail=message)
        elif source == "smartthings" and st_device_id:
            from common import st_utils

            mapped = st_utils.translate_generic_control_params(device_type, command, data.params)
            if mapped is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported command '{command}' for device type '{device_type}'",
                )
            capability, st_command, args = mapped
            success, message = st_utils.st_control_device(
                st_device_id, capability, st_command, args
            )
            if success:
                devices = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_iot_devices_data
                )
                await manager.broadcast("iot_devices", devices)
                return {
                    "message": message,
                    "device_id": device_id,
                    "command": command,
                    "device_type": device_type,
                }
            else:
                raise HTTPException(status_code=500, detail=message)
        else:
            raise HTTPException(status_code=400, detail="Unsupported source or device")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error controlling IoT device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/iot/devices/{device_id}/link")
async def link_iot_device(
    device_id: int, data: LinkDevice, _perm=Depends(require_permission("iot", "link"))
):
    try:
        with db_connection() as db:
            cursor = db.cursor()

            cursor.execute("SELECT id, name FROM smarthome_devices WHERE id = %s", (device_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="IoT device not found")

            if data.device_id is None:
                cursor.execute(
                    "UPDATE smarthome_devices SET device_id = NULL WHERE id = %s",
                    (device_id,),
                )
                db.commit()
                unlinked = True
            else:
                cursor.execute("SELECT id, name FROM device WHERE id = %s", (data.device_id,))
                target_row = cursor.fetchone()
                if not target_row:
                    raise HTTPException(status_code=404, detail="Target device not found")

                cursor.execute(
                    "UPDATE smarthome_devices SET device_id = %s WHERE id = %s",
                    (data.device_id, device_id),
                )
                db.commit()
                unlinked = False

        devices = await asyncio.get_event_loop().run_in_executor(None, fetch_iot_devices_data)
        await manager.broadcast("iot_devices", devices)
        if unlinked:
            return {"message": "Device unlinked", "device_id": device_id}
        return {
            "message": "Device linked",
            "device_id": device_id,
            "linked_to": data.device_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking IoT device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iot/providers")
async def get_iot_providers():
    """HA/SmartThings are listed here because `iot_provider` (below) picks a single default
    between them. ESPHome isn't -- it runs always-on in parallel regardless of that selection
    (todo/todo_esphome.md Design section 5), so it's surfaced via /iot/esphome/status instead."""
    return [
        {"id": "homeassistant", "name": "Home Assistant", "status": "configured"},
        {"id": "smartthings", "name": "SmartThings", "status": "not_configured"},
    ]


@router.put("/iot/provider")
async def set_iot_provider(
    data: IoTProvider, _perm=Depends(require_permission("iot", "set_provider"))
):
    if data.provider not in ["homeassistant", "smartthings"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = 'iot_provider'", (data.provider,)
            )
            db.commit()
        return {"message": f"Provider set to {data.provider}"}
    except Exception as e:
        logger.error(f"Error setting IoT provider: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
