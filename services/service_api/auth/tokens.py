"""Opaque refresh-token issue/lookup/revoke against the refresh_tokens table.

Only a SHA-256 hash of the token is ever stored -- the raw value is returned to the caller once
(at issue time) and never persisted, so a DB read alone can't be replayed. Uses the same raw
pymysql + `with db_connection() as db:` pattern as every other module in this codebase (no ORM).
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from common import db_connection

REFRESH_TOKEN_TTL_DAYS = 30


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
