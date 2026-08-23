"""Stateless JWT access tokens for ALFR3D auth.

Signed with the same key material secrets_utils.py already provisions for Fernet encryption
(see get_signing_key_bytes()) so this doesn't need its own key-file infrastructure. Access
tokens are short-lived and never stored server-side -- only the paired refresh token
(auth/tokens.py) is, so it can be revoked.
"""

from datetime import datetime, timedelta, timezone

import jwt

from common import secrets_utils

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = 15


def create_access_token(user_id, user_type, ttl_minutes=ACCESS_TOKEN_TTL_MINUTES):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": user_type,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secrets_utils.get_signing_key_bytes(), algorithm=ALGORITHM)


def decode_access_token(token):
    """Returns the decoded payload dict, or None if the token is missing/expired/invalid.
    Never raises -- callers (auth dependencies) treat None as "not authenticated"."""
    try:
        return jwt.decode(token, secrets_utils.get_signing_key_bytes(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
