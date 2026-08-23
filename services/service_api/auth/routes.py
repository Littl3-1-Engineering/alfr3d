"""Auth routes: login, refresh, logout, the Phase-0 account-claim bootstrap, and Phase-5
password change/reset.

POST /api/auth/claim exists because no existing `user` row had a password before this feature
shipped (per todo/todo_auth_rbac.md's Phase 0) -- it's unauthenticated but narrowly scoped: it
only ever sets a password for a user whose password_hash is currently NULL/empty, so it can't be
used to take over an already-claimed account.

Rate limiting (Phase 5): `login` and `claim` are throttled via auth/rate_limit.py, which fails
open if Redis is unavailable -- see that module's own doc for why. `refresh`/`logout` aren't
throttled: a refresh token is itself a high-entropy secret (not a guessable username/password
pair), and logout is idempotent/self-limiting by nature.
"""

import logging

import pymysql
from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import db_connection
from models import (
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    ClaimAccountRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
)
from auth import jwt_utils, password_utils, tokens
from auth.dependencies import CurrentUser, require_auth, require_permission
from auth.rate_limit import check_rate_limit

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
CLAIM_MAX_ATTEMPTS = 10
CLAIM_WINDOW_SECONDS = 15 * 60


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited() -> HTTPException:
    return HTTPException(status_code=429, detail="Too many attempts, try again later")


def _validate_new_password(password):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")


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
async def login(data: LoginRequest, request: Request):
    # Keyed by IP+username, not IP alone, so one household member mistyping their password
    # repeatedly can't lock out everyone else on the same LAN/NAT.
    rate_key = f"ratelimit:login:{_client_ip(request)}:{data.username}"
    if not check_rate_limit(rate_key, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS):
        raise _rate_limited()

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
async def claim_account(data: ClaimAccountRequest, request: Request):
    rate_key = f"ratelimit:claim:{_client_ip(request)}"
    if not check_rate_limit(rate_key, CLAIM_MAX_ATTEMPTS, CLAIM_WINDOW_SECONDS):
        raise _rate_limited()

    _validate_new_password(data.password)

    # A single generic error for "no such user" and "already claimed" -- returning distinct
    # 404/409s here would let a caller enumerate which usernames exist and which are already
    # claimed, the same category of leak login's uniform 401 already avoids.
    unable_to_claim = HTTPException(status_code=400, detail="Unable to claim this account")

    with db_connection() as db:
        cursor = db.cursor()
        row = _user_by_username(cursor, data.username)
        if not row:
            raise unable_to_claim
        user_id, existing_hash, user_type = row
        if existing_hash:
            raise unable_to_claim

        cursor.execute(
            "UPDATE user SET password_hash = %s WHERE id = %s",
            (password_utils.hash_password(data.password), user_id),
        )
        db.commit()

    return _issue_tokens(user_id, user_type)


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, user: CurrentUser = Depends(require_auth)):
    """Self-service password change for the caller's own account -- `user.id` comes from the
    verified access token, never a body param, so there's no way to pass someone else's id."""
    _validate_new_password(data.new_password)

    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute("SELECT password_hash FROM user WHERE id = %s", (user.id,))
        row = cursor.fetchone()
        if not row or not password_utils.verify_password(data.current_password, row[0]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        cursor.execute(
            "UPDATE user SET password_hash = %s WHERE id = %s",
            (password_utils.hash_password(data.new_password), user.id),
        )
        db.commit()

    # Every other session is forced to re-login -- the expected security property after a
    # password change (deliberate or because it may have been compromised). A fresh token pair
    # is returned so the caller's own current session keeps working without a forced re-login.
    tokens.revoke_all_refresh_tokens(user.id)
    return _issue_tokens(user.id, user.type)


@router.post("/admin-reset-password")
async def admin_reset_password(
    data: AdminResetPasswordRequest, _perm=Depends(require_permission("users"))
):
    """Technoking-only recovery path for "I forgot my password" -- no email/SMTP capability
    exists in this codebase, so a traditional emailed-reset-link flow is out of scope; this
    mirrors the household trust model already used for user management elsewhere (see
    auth/permissions.py's `"users": {"*": _TECHNOKING_ONLY}`)."""
    _validate_new_password(data.new_password)

    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM user WHERE id = %s", (data.user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        cursor.execute(
            "UPDATE user SET password_hash = %s WHERE id = %s",
            (password_utils.hash_password(data.new_password), data.user_id),
        )
        db.commit()

    tokens.revoke_all_refresh_tokens(data.user_id)
    return {"success": True}
