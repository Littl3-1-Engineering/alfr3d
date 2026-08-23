"""Auth routes: login, refresh, logout, and the Phase-0 account-claim bootstrap.

POST /api/auth/claim exists because no existing `user` row had a password before this feature
shipped (per todo/todo_auth_rbac.md's Phase 0) -- it's unauthenticated but narrowly scoped: it
only ever sets a password for a user whose password_hash is currently NULL/empty, so it can't be
used to take over an already-claimed account. Full rate-limiting on all of these is Phase 5,
deferred; this endpoint's own guard is the load-bearing protection for now.
"""

import logging

import pymysql
from fastapi import APIRouter, HTTPException

from dependencies import db_connection
from models import ClaimAccountRequest, LoginRequest, LogoutRequest, RefreshRequest
from auth import jwt_utils, password_utils, tokens

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_by_username(cursor, username):
    cursor.execute(
        "SELECT u.id, u.password_hash, ut.type FROM user u "
        "JOIN user_types ut ON u.type = ut.id WHERE u.username = %s",
        (username,),
    )
    return cursor.fetchone()


def _issue_tokens(user_id, user_type):
    return {
        "access_token": jwt_utils.create_access_token(user_id, user_type),
        "refresh_token": tokens.issue_refresh_token(user_id),
        "token_type": "bearer",
    }


@router.post("/login")
async def login(data: LoginRequest):
    try:
        with db_connection() as db:
            cursor = db.cursor()
            row = _user_by_username(cursor, data.username)
    except pymysql.Error as e:
        logger.error(f"Error looking up user for login: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

    if not row or not password_utils.verify_password(data.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_id, _password_hash, user_type = row
    return _issue_tokens(user_id, user_type)


@router.post("/refresh")
async def refresh(data: RefreshRequest):
    user_id = tokens.redeem_refresh_token(data.refresh_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT ut.type FROM user u JOIN user_types ut ON u.type = ut.id WHERE u.id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User no longer exists")

    tokens.revoke_refresh_token(data.refresh_token)
    return _issue_tokens(user_id, row[0])


@router.post("/logout")
async def logout(data: LogoutRequest):
    tokens.revoke_refresh_token(data.refresh_token)
    return {"success": True}


@router.post("/claim")
async def claim_account(data: ClaimAccountRequest):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    with db_connection() as db:
        cursor = db.cursor()
        row = _user_by_username(cursor, data.username)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, existing_hash, user_type = row
        if existing_hash:
            raise HTTPException(status_code=409, detail="Account already claimed")

        cursor.execute(
            "UPDATE user SET password_hash = %s WHERE id = %s",
            (password_utils.hash_password(data.password), user_id),
        )
        db.commit()

    return _issue_tokens(user_id, user_type)
