"""Unit tests for services/common/secrets_utils.py.

Pure unit tests, no DB/Kafka -- mirrors test_esphome_utils.py's style. Uses a temp directory for
the key file so tests never touch a real /secrets mount, and resets the module's cached Fernet
instance between tests since it's a lazy module-level singleton.
"""

import os

import pytest
from cryptography.fernet import Fernet

from common import secrets_utils


@pytest.fixture(autouse=True)
def _reset_module_state(tmp_path, monkeypatch):
    """Every test gets an isolated key path and a clean singleton cache."""
    monkeypatch.delenv("ALFR3D_SECRETS_KEY", raising=False)
    monkeypatch.setenv("ALFR3D_SECRETS_KEY_PATH", str(tmp_path / "secrets" / "key"))
    secrets_utils._fernet = None
    yield
    secrets_utils._fernet = None


# --- Key resolution -------------------------------------------------------------------------


def test_env_var_key_takes_precedence_over_file(tmp_path, monkeypatch):
    env_key = Fernet.generate_key()
    monkeypatch.setenv("ALFR3D_SECRETS_KEY", env_key.decode())
    assert secrets_utils.get_secrets_key_bytes() == env_key


def test_generates_and_persists_key_on_first_call():
    key_path = secrets_utils._key_path()
    assert not os.path.exists(key_path)
    key = secrets_utils.get_secrets_key_bytes()
    assert os.path.exists(key_path)
    with open(key_path, "rb") as f:
        assert f.read().strip() == key


def test_second_call_reuses_persisted_key_instead_of_regenerating():
    first = secrets_utils.get_secrets_key_bytes()
    secrets_utils._fernet = None  # force re-resolution, simulating a fresh process
    second = secrets_utils.get_secrets_key_bytes()
    assert first == second


# --- encrypt/decrypt --------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    plaintext = "sk-super-secret-token-value"
    ciphertext = secrets_utils.encrypt(plaintext)
    assert ciphertext != plaintext
    assert secrets_utils.decrypt(ciphertext) == plaintext


def test_encrypt_none_returns_none():
    assert secrets_utils.encrypt(None) is None


def test_decrypt_or_plaintext_returns_decrypted_value_for_encrypted_input():
    ciphertext = secrets_utils.encrypt("my-token")
    assert secrets_utils.decrypt_or_plaintext(ciphertext) == "my-token"


def test_decrypt_or_plaintext_falls_back_to_original_value_for_legacy_plaintext():
    """The dual-read migration path: rows written before this module existed are still
    plaintext, not a Fernet token -- decrypt_or_plaintext must return them unchanged rather
    than raising, so the read path never breaks on old data."""
    assert secrets_utils.decrypt_or_plaintext("plain-old-ha-token") == "plain-old-ha-token"


def test_decrypt_or_plaintext_returns_falsy_values_unchanged():
    assert secrets_utils.decrypt_or_plaintext("") == ""
    assert secrets_utils.decrypt_or_plaintext(None) is None
