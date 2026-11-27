"""Encrypt-at-rest for camera RTSP URLs (``device.stream_url``).

The URL embeds the camera account's username/password, so the whole value is stored as a Fernet
token (``common/secrets_utils.py``). Writes encrypt; the only readers (ffmpeg start + snapshot in
``routes/stream.py``) decrypt at the point of use. Rows written before this existed are still
plaintext and keep working through ``decrypt_or_plaintext``; ``encrypt_existing_stream_urls``
converts them in place at API startup (the migrate container has no secrets volume, so this can't
be an alembic migration). Idempotent: already-encrypted rows are skipped.
"""

import logging
import re

from common import secrets_utils

logger = logging.getLogger("ApiLog")

_PLAIN_PREFIXES = ("rtsp://", "rtsps://")
# user:password@ in a URL, for scrubbing ffmpeg stderr before it reaches the logs.
_CREDS_RE = re.compile(r"(rtsps?://)[^/\s@]+@", re.IGNORECASE)


def encrypt_stream_url(url):
    """Encrypt a plaintext URL for storage. Falsy -> None; already-encrypted values pass through."""
    if not url:
        return None
    if not url.lower().startswith(_PLAIN_PREFIXES):
        return url
    return secrets_utils.encrypt(url)


def decrypt_stream_url(stored):
    return secrets_utils.decrypt_or_plaintext(stored)


def redact_credentials(text):
    return _CREDS_RE.sub(r"\1***@", text)


def encrypt_existing_stream_urls(db_connection):
    """Encrypt any plaintext stream_url rows in place. Returns the number converted."""
    converted = 0
    with db_connection() as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, stream_url FROM device "
            "WHERE stream_url IS NOT NULL AND (stream_url LIKE 'rtsp://%' "
            "OR stream_url LIKE 'rtsps://%')"
        )
        for device_id, url in cursor.fetchall():
            cursor.execute(
                "UPDATE device SET stream_url = %s WHERE id = %s",
                (secrets_utils.encrypt(url), device_id),
            )
            converted += 1
        if converted:
            db.commit()
    if converted:
        logger.info(f"Encrypted {converted} plaintext camera stream_url value(s) at rest")
    return converted
