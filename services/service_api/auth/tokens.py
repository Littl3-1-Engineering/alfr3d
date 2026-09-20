"""Opaque refresh-token issue/lookup/revoke against the refresh_tokens table.

Only a SHA-256 hash of the token is ever stored -- the raw value is returned to the caller once
(at issue time) and never persisted, so a DB read alone can't be replayed. Uses the same raw
pymysql + `with db_connection() as db:` pattern as every other module in this codebase (no ORM).

Rotation grace window: refresh tokens are one-time-use (redeemed -> immediately revoked), so two
callers racing to refresh off the same stored token -- e.g. two of the Deck app's background
pollers noticing the same expired access token within milliseconds of each other -- always leave
a loser trying to redeem an already-revoked token. Observed live 2026-09-20: the loser's 401
permanently killed the Deck app's session (no further refresh attempts for hours) rather than
just failing that one poll. `cache_rotation_result`/`get_cached_rotation_result` give the loser
the same rotated pair the winner already got instead of a 401 -- same fail-soft Redis pattern as
`auth/rate_limit.py`.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from common import db_connection, redis_get, redis_set

REFRESH_TOKEN_TTL_DAYS = 30
REFRESH_GRACE_SECONDS = 10


def _hash(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_refresh_token(user_id):
    """Creates a new refresh token row and returns the raw (opaque) token string."""
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user_id, _hash(raw_token), expires_at),
        )
        db.commit()
    return raw_token


def _grace_cache_key(raw_token):
    return f"refresh_grace:{_hash(raw_token)}"


def cache_rotation_result(raw_token, result):
    """Caches the token pair issued for redeeming raw_token, keyed by that (now-revoked) token's
    hash, so a duplicate redemption within REFRESH_GRACE_SECONDS replays the same result instead
    of 401ing."""
    redis_set(_grace_cache_key(raw_token), result, ttl=REFRESH_GRACE_SECONDS)


def get_cached_rotation_result(raw_token):
    return redis_get(_grace_cache_key(raw_token))


def redeem_refresh_token(raw_token):
    """Returns the user_id for a valid, unexpired, unrevoked refresh token, or None."""
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT user_id FROM refresh_tokens "
            "WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > UTC_TIMESTAMP()",
            (_hash(raw_token),),
        )
        row = cursor.fetchone()
    return row[0] if row else None


def revoke_refresh_token(raw_token):
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE refresh_tokens SET revoked_at = UTC_TIMESTAMP() "
            "WHERE token_hash = %s AND revoked_at IS NULL",
            (_hash(raw_token),),
        )
        db.commit()


def revoke_all_refresh_tokens(user_id):
    """Revokes every still-active refresh token for a user -- used after a password change/reset
    so every other session is forced to re-login, the expected security property when a password
    was just changed (deliberately, or because it may have been compromised)."""
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE refresh_tokens SET revoked_at = UTC_TIMESTAMP() "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )
        db.commit()
