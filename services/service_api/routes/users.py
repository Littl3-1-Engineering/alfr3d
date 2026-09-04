"""User management routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
import pymysql

from dependencies import (
    db_connection,
    _get_cached_or_fetch,
    _invalidate_cache_pattern,
    manager,
    ALFR3D_ENV_NAME,
)
from models import UserCreate, UserUpdate
from auth import permissions
from auth.dependencies import CurrentUser, require_auth, require_permission

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users")
async def get_users(online: bool = Query(False)):
    try:
        from dependencies import _fetch_users

        users = _get_cached_or_fetch(f"api:users:{ALFR3D_ENV_NAME}", _fetch_users, ttl=120)
        if online:
            users = [u for u in users if u.get("state") == "online"]
        await manager.broadcast("users", users)
        return users
    except pymysql.Error as e:
        logger.error(f"Error fetching users: {str(e)}")
        mock_users = (
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
            ]
            if online
            else [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "offline",
                    "last_online": "",
                },
            ]
        )
        return mock_users


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, _perm=Depends(require_permission("users", "create"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM states WHERE state = 'offline'")
            state_row = cursor.fetchone()
            if not state_row:
                raise HTTPException(status_code=500, detail="Offline state not found")
            state_id = state_row[0]
            cursor.execute("SELECT id FROM user_types WHERE type = %s", (data.type,))
            type_row = cursor.fetchone()
            if not type_row:
                raise HTTPException(status_code=400, detail="Invalid user type")
            type_id = type_row[0]
            cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            env_row = cursor.fetchone()
            if not env_row:
                raise HTTPException(status_code=500, detail="Environment not found")
            env_id = env_row[0]
            cursor.execute(
                "INSERT INTO user (username, email, about_me, title, created_at, state, type, "
                "environment_id) "
                "VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s)",
                (data.name, data.email, data.about_me, data.title, state_id, type_id, env_id),
            )
            db.commit()
            new_id = cursor.lastrowid
        _invalidate_cache_pattern(f"api:users:{ALFR3D_ENV_NAME}")
        return {"id": new_id, "name": data.name, "type": data.type}
    except pymysql.Error as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, user: CurrentUser = Depends(require_auth)):
    """Owner/technoking can edit any user (full field set, including `type`). Any authenticated
    user can also edit their *own* row this same way -- but never `type`, even if they're also an
    owner/technoking: self-promotion/demotion must go through the explicit admin-on-someone-else
    path, never slip in on a profile edit. See todo/todo_user_management.md's locked decision."""
    is_self = user.id == user_id
    is_admin = permissions.is_allowed("users", "update", user.type)
    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Not permitted")
    requested_type = data.type if (is_admin and not is_self) else None

    try:
        with db_connection() as db:
            cursor = db.cursor()
            updates = []
            params = []
            if data.name is not None:
                updates.append("username = %s")
                params.append(data.name)
            if data.email is not None:
                updates.append("email = %s")
                params.append(data.email)
            if data.about_me is not None:
                updates.append("about_me = %s")
                params.append(data.about_me)
            if data.title is not None:
                updates.append("title = %s")
                params.append(data.title)
            if requested_type is not None:
                cursor.execute("SELECT id FROM user_types WHERE type = %s", (requested_type,))
                type_id = cursor.fetchone()
                if type_id:
                    updates.append("type = %s")
                    params.append(type_id[0])
            if updates:
                params.append(user_id)
                cursor.execute(f"UPDATE user SET {', '.join(updates)} WHERE id = %s", params)
                db.commit()
        _invalidate_cache_pattern(f"api:users:{ALFR3D_ENV_NAME}")
        return {"message": "User updated"}
    except pymysql.Error as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, _perm=Depends(require_permission("users", "delete"))):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
            db.commit()
        _invalidate_cache_pattern(f"api:users:{ALFR3D_ENV_NAME}")
        return {"message": "User deleted"}
    except pymysql.Error as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
