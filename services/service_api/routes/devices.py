"""Device management routes."""

import logging
from fastapi import APIRouter, HTTPException
import pymysql

from dependencies import (
    get_connection,
    get_cache,
    _get_cached_or_fetch,
    _invalidate_cache_pattern,
    manager,
    ALFR3D_ENV_NAME,
)
from models import DeviceCreate, DeviceUpdate

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["devices"])


@router.get("/devices")
async def get_devices():
    try:
        from dependencies import _fetch_devices

        devices = _get_cached_or_fetch(f"api:devices:{ALFR3D_ENV_NAME}", _fetch_devices, ttl=120)
        await manager.broadcast("devices", devices)
        return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users-with-devices")
async def get_users_with_devices():
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute(
            """
            SELECT u.id, u.username as name, u.email, u.about_me, s.state, ut.type,
                   u.last_online, u.created_at
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            JOIN environment e ON u.environment_id = e.id
            WHERE e.name = %s AND u.username NOT IN ('unknown', 'alfr3d')
            ORDER BY u.last_online DESC
            """,
            (ALFR3D_ENV_NAME,),
        )
        users = cursor.fetchall()

        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, ds.state AS device_state,
                   dt.type, d.user_id, d.last_online
            FROM device d
            JOIN states ds ON d.state = ds.id
            JOIN device_types dt ON d.device_type = dt.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            ORDER BY d.last_online DESC
            """,
            (ALFR3D_ENV_NAME,),
        )
        devices = cursor.fetchall()
        db.close()

        devices_by_user = {}
        for d in devices:
            uid = d.pop("user_id")
            if uid not in devices_by_user:
                devices_by_user[uid] = []
            devices_by_user[uid].append(d)

        user_ids = {u["id"] for u in users}
        unassigned_devices = devices_by_user.get(None, []) + [
            d
            for uid, devs in devices_by_user.items()
            if uid is not None and uid not in user_ids
            for d in devs
        ]
        for device in unassigned_devices:
            device["state"] = device.pop("device_state")
            if device.get("last_online"):
                device["last_online"] = device["last_online"].isoformat()

        for user in users:
            user["devices"] = devices_by_user.get(user["id"], [])
            for device in user.get("devices", []):
                device["state"] = device.pop("device_state")
                if device.get("last_online"):
                    device["last_online"] = device["last_online"].isoformat()
            if user.get("last_online"):
                user["last_online"] = user["last_online"].isoformat()
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()

        return {"users": users, "unassigned_devices": unassigned_devices}
    except Exception as e:
        logger.error(f"Error fetching users with devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/device-types")
async def get_device_types():
    cache = get_cache()
    cache_key = "api_device_types"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, type FROM device_types")
        types = [{"id": row[0], "type": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, types, ttl=300)
        return types
    except pymysql.Error as e:
        logger.error(f"Error fetching device types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user-types")
async def get_user_types():
    cache = get_cache()
    cache_key = "api_user_types"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, type FROM user_types")
        types = [{"id": row[0], "type": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, types, ttl=300)
        return types
    except pymysql.Error as e:
        logger.error(f"Error fetching user types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/states")
async def get_states():
    cache = get_cache()
    cache_key = "api_states"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id, state FROM states")
        states = [{"id": row[0], "state": row[1]} for row in cursor.fetchall()]
        db.close()
        cache.set(cache_key, states, ttl=300)
        return states
    except pymysql.Error as e:
        logger.error(f"Error fetching states: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices", status_code=201)
async def create_device(data: DeviceCreate):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM states WHERE state = 'offline'")
        state_row = cursor.fetchone()
        if not state_row:
            raise HTTPException(status_code=500, detail="Offline state not found")
        state_id = state_row[0]
        cursor.execute("SELECT id FROM device_types WHERE type = %s", (data.type,))
        type_row = cursor.fetchone()
        if not type_row:
            raise HTTPException(status_code=400, detail="Invalid device type")
        type_id = type_row[0]
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            raise HTTPException(status_code=500, detail="Environment not found")
        env_id = env_row[0]
        user_id = None
        if data.user:
            cursor.execute("SELECT id FROM user WHERE username = %s", (data.user,))
            user_row = cursor.fetchone()
            if user_row:
                user_id = user_row[0]
        cursor.execute(
            "INSERT INTO device (name, IP, MAC, state, device_type, user_id, environment_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (data.name, data.ip, data.mac, state_id, type_id, user_id, env_id),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        _invalidate_cache_pattern(f"api:devices:{ALFR3D_ENV_NAME}")
        return {"id": new_id, "name": data.name, "type": data.type}
    except pymysql.Error as e:
        logger.error(f"Error creating device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    try:
        db = get_connection()
        cursor = db.cursor()
        updates = []
        params = []
        if data.name is not None:
            updates.append("name = %s")
            params.append(data.name)
        if data.ip is not None:
            updates.append("IP = %s")
            params.append(data.ip)
        if data.mac is not None:
            updates.append("MAC = %s")
            params.append(data.mac)
        if data.type is not None:
            cursor.execute("SELECT id FROM device_types WHERE type = %s", (data.type,))
            type_row = cursor.fetchone()
            if type_row:
                updates.append("device_type = %s")
                params.append(type_row[0])
        if data.user is not None:
            if data.user:
                cursor.execute("SELECT id FROM user WHERE username = %s", (data.user,))
                user_row = cursor.fetchone()
                if user_row:
                    updates.append("user_id = %s")
                    params.append(user_row[0])
            else:
                updates.append("user_id = NULL")
        if data.position is not None:
            if "x" in data.position and "y" in data.position:
                updates.append("position_x = %s")
                params.append(data.position["x"])
                updates.append("position_y = %s")
                params.append(data.position["y"])
            else:
                updates.append("position_x = NULL")
                updates.append("position_y = NULL")
        if updates:
            params.append(device_id)
            cursor.execute(f"UPDATE device SET {', '.join(updates)} WHERE id = %s", params)
            db.commit()
        db.close()
        _invalidate_cache_pattern(f"api:devices:{ALFR3D_ENV_NAME}")
        return {"message": "Device updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM device WHERE id = %s", (device_id,))
        db.commit()
        db.close()
        _invalidate_cache_pattern(f"api:devices:{ALFR3D_ENV_NAME}")
        return {"message": "Device deleted"}
    except pymysql.Error as e:
        logger.error(f"Error deleting device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/devices")
async def get_user_devices(user_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, d.last_online, u.username
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            WHERE d.user_id = %s
            """,
            (user_id,),
        )
        devices = [
            {
                "id": row[0],
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "last_online": str(row[6]),
                "user": row[7],
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return devices
    except pymysql.Error as e:
        logger.error(f"Error fetching user devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/history")
async def get_device_history(device_id: int):
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT dh.timestamp, dh.name, dh.IP, dh.MAC, s.state,
                   dt.type, u.username, dh.last_online
            FROM device_history dh
            LEFT JOIN states s ON dh.state = s.id
            LEFT JOIN device_types dt ON dh.device_type = dt.id
            LEFT JOIN user u ON dh.user_id = u.id
            WHERE dh.device_id = %s
            ORDER BY dh.timestamp DESC
            """,
            (device_id,),
        )
        history = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "user": row[6],
                "last_online": row[7].isoformat() if row[7] else None,
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return history
    except pymysql.Error as e:
        logger.error(f"Error fetching device history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
