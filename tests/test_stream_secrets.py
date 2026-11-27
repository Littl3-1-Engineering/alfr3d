"""Camera RTSP URL encryption at rest (todo_rtsp_stream_url_secret_store.md)."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from common import secrets_utils

import stream_secrets as ss

URL = "rtsp://cam_user:s3cret@10.0.0.50/stream1"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("ALFR3D_SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(secrets_utils, "_fernet", None)


def test_round_trip_and_not_plaintext():
    stored = ss.encrypt_stream_url(URL)
    assert "s3cret" not in stored and not stored.startswith("rtsp")
    assert ss.decrypt_stream_url(stored) == URL


def test_falsy_and_already_encrypted_pass_through():
    assert ss.encrypt_stream_url("") is None
    assert ss.encrypt_stream_url(None) is None
    stored = ss.encrypt_stream_url(URL)
    assert ss.encrypt_stream_url(stored) == stored


def test_legacy_plaintext_still_readable():
    assert ss.decrypt_stream_url(URL) == URL


def test_encrypted_fits_column_at_validator_limit():
    url = "rtsp://" + "a" * 293  # 300 chars
    assert len(ss.encrypt_stream_url(url)) <= 512


def test_redact_credentials():
    out = ss.redact_credentials(f"Error opening {URL}: refused")
    assert "s3cret" not in out and "cam_user" not in out and "10.0.0.50" in out


def test_backfill_mixed_rows():
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, URL), (2, "rtsps://u:p@h/x")]
    db = MagicMock()
    db.cursor.return_value = cursor

    @contextmanager
    def conn():
        yield db

    assert ss.encrypt_existing_stream_urls(conn) == 2
    updates = [c.args for c in cursor.execute.call_args_list if c.args[0].startswith("UPDATE")]
    assert len(updates) == 2
    assert ss.decrypt_stream_url(updates[0][1][0]) == URL
    db.commit.assert_called_once()


def test_backfill_nothing_to_do_does_not_commit():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    db = MagicMock()
    db.cursor.return_value = cursor

    @contextmanager
    def conn():
        yield db

    assert ss.encrypt_existing_stream_urls(conn) == 0
    db.commit.assert_not_called()


def test_validator_rejects_overlong():
    from models import _validate_stream_url

    with pytest.raises(ValueError):
        _validate_stream_url("rtsp://" + "a" * 300)


def test_every_top_level_api_module_is_copied_into_the_image():
    """service_api/Dockerfile copies files one by one; a new top-level module missing there
    imports fine in CI and crash-loops the container (PR #495 on the NUC, 2026-11-27)."""
    from pathlib import Path

    api = Path(__file__).parent.parent / "services" / "service_api"
    dockerfile = (api / "Dockerfile").read_text()
    missing = [
        p.name
        for p in api.glob("*.py")
        if f"COPY service_api/{p.name} " not in dockerfile and p.name != "__init__.py"
    ]
    assert missing == [], f"not in service_api/Dockerfile: {missing}"
