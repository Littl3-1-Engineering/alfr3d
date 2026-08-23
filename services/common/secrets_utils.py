"""Encrypt-at-rest helpers for integration credentials (ha_token, st_pat,
spotify_client_secret, ESPHome node PSKs).

Key resolution order: the ``ALFR3D_SECRETS_KEY`` env var (an explicit
override, e.g. for k8s secret injection) takes precedence; otherwise a key
is read from -- or generated and persisted to -- a file at
``ALFR3D_SECRETS_KEY_PATH`` (default ``/secrets/alfr3d_secrets.key``, a
Docker volume shared by every service that touches secrets). This is a
deliberate zero-config choice for the ALFR3D Kit hardware SKU: a
non-technical buyer gets a working device with no setup step. The
tradeoff is explicit and accepted -- losing that volume makes every stored
credential permanently unrecoverable; they must be re-entered from the UI.
There is no key-rotation story for v1.

``decrypt_or_plaintext()`` is what makes rollout zero-downtime: every
``get_*_config`` should call it instead of ``decrypt()`` directly, so rows
written before this module existed (still plaintext) keep working. Every
``save_*_config``/write path should call ``encrypt()`` so all new writes
are encrypted going forward -- the database self-heals to fully-encrypted
as each credential gets naturally rewritten (e.g. next OAuth refresh).
Some rows may stay plaintext indefinitely if never rewritten; that's an
accepted tradeoff given the threat model is "DB dump leak," not "every row
encrypted by date X."
"""

import logging
import os
import time

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("SecretsLog")

DEFAULT_KEY_PATH = "/secrets/alfr3d_secrets.key"

_fernet = None


def _key_path():
    return os.environ.get("ALFR3D_SECRETS_KEY_PATH", DEFAULT_KEY_PATH)


def _read_key_from_env():
    env_key = os.environ.get("ALFR3D_SECRETS_KEY")
    return env_key.encode() if env_key else None


def _read_key_from_file(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read().strip()


def _generate_and_persist_key(path):
    """Atomically create the key file so concurrent services racing on
    first boot can't clobber each other's key. The loser of the race just
    reads back what the winner wrote."""
    new_key = Fernet.generate_key()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        # 0o644, not 0o600: service-api/service-daemon run as uid 1000 but
        # service-device runs as root (needs raw network access for
        # arp-scan) -- whichever service wins the creation race would
        # otherwise lock the other uid out of a 0600 file. The shared
        # Docker volume mount is the actual access-control boundary here,
        # not the in-container file mode.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(new_key)
        logger.warning(
            f"Generated new ALFR3D_SECRETS_KEY at {path} -- back up this volume; "
            "losing it makes every stored integration credential unrecoverable "
            "and they must be re-entered from the UI."
        )
        return new_key
    except FileExistsError:
        return _read_key_from_file(path)
    except PermissionError:
        # Only service-api ever writes secrets (it owns every save_*_config
        # route) and its entrypoint chowns this volume to its uid before the
        # app starts -- but another, differently-uid'd service could in
        # theory hit this generation path first on a completely fresh
        # volume (e.g. reading a legacy plaintext row). Rather than crash,
        # give service-api's entrypoint a brief window to win the race and
        # create the file, then fail loudly if it still hasn't.
        for _ in range(10):
            time.sleep(0.5)
            key = _read_key_from_file(path)
            if key:
                return key
        raise RuntimeError(
            f"Could not create or read the secrets key at {path}: permission denied, "
            "and no key appeared after waiting. Check the secrets_data volume's ownership."
        )


def get_secrets_key_bytes():
    """Resolve (or provision) the raw Fernet key bytes. Also usable as
    signing key material for other symmetric needs (e.g. JWT HS256) so
    they don't need their own key-file infrastructure."""
    key = _read_key_from_env()
    if key:
        return key
    path = _key_path()
    key = _read_key_from_file(path)
    if key:
        return key
    return _generate_and_persist_key(path)


def get_signing_key_bytes():
    """Alias for get_secrets_key_bytes(), for callers using this key as HMAC signing
    material (e.g. JWT access tokens) rather than for Fernet encryption -- same key
    infrastructure, different use, so it doesn't need its own key-file provisioning."""
    return get_secrets_key_bytes()


def _get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_secrets_key_bytes())
    return _fernet


def encrypt(value):
    if value is None:
        return value
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value):
    return _get_fernet().decrypt(value.encode()).decode()


def decrypt_or_plaintext(value):
    """Try to decrypt; on any failure (not a Fernet token -- i.e. still
    plaintext from before this module existed) return the value unchanged."""
    if not value:
        return value
    try:
        return decrypt(value)
    except (InvalidToken, ValueError):
        return value
