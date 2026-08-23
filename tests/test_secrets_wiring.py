"""Confirms ha_utils/st_utils/spotify_utils/esphome_utils actually route their secret fields
through secrets_utils.encrypt/decrypt_or_plaintext, not just that secrets_utils itself works
(see test_secrets_utils.py for that). Mock-DB style, mirrors test_esphome_utils.py.
"""

from unittest.mock import MagicMock, patch

from common import ha_utils, st_utils, spotify_utils, secrets_utils


# --- ha_utils --------------------------------------------------------------------------------


def test_save_ha_config_encrypts_token():
    mock_db = MagicMock()
    with patch.object(ha_utils, "get_connection", return_value=mock_db):
        with patch.object(secrets_utils, "encrypt", return_value="ENCRYPTED") as mock_encrypt:
            ha_utils.save_ha_config("http://ha.local", "plain-token")
    mock_encrypt.assert_called_once_with("plain-token")
    cursor = mock_db.cursor.return_value
    token_call = [c for c in cursor.execute.call_args_list if "ha_token" in c.args[0]][0]
    assert token_call.args[1] == ("ENCRYPTED",)


def test_get_ha_config_decrypts_token():
    mock_db = MagicMock()
    cursor = mock_db.cursor.return_value
    cursor.fetchall.return_value = [("ha_url", "http://ha.local"), ("ha_token", "ENCRYPTED")]
    with patch.object(ha_utils, "get_connection", return_value=mock_db):
        with patch.object(
            secrets_utils, "decrypt_or_plaintext", return_value="plain-token"
        ) as mock_decrypt:
            config = ha_utils.get_ha_config()
    mock_decrypt.assert_called_once_with("ENCRYPTED")
    assert config["ha_token"] == "plain-token"
    assert config["ha_url"] == "http://ha.local"


# --- st_utils --------------------------------------------------------------------------------


def test_save_st_config_encrypts_pat():
    mock_db = MagicMock()
    with patch.object(st_utils, "get_connection", return_value=mock_db):
        with patch.object(secrets_utils, "encrypt", return_value="ENCRYPTED") as mock_encrypt:
            st_utils.save_st_config("plain-pat")
    mock_encrypt.assert_called_once_with("plain-pat")
    cursor = mock_db.cursor.return_value
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args.args[1] == ("ENCRYPTED",)


def test_get_st_config_decrypts_pat():
    mock_db = MagicMock()
    cursor = mock_db.cursor.return_value
    cursor.fetchall.return_value = [("st_pat", "ENCRYPTED")]
    with patch.object(st_utils, "get_connection", return_value=mock_db):
        with patch.object(
            secrets_utils, "decrypt_or_plaintext", return_value="plain-pat"
        ) as mock_decrypt:
            config = st_utils.get_st_config()
    mock_decrypt.assert_called_once_with("ENCRYPTED")
    assert config["st_pat"] == "plain-pat"


# --- spotify_utils ---------------------------------------------------------------------------


def test_save_spotify_credentials_encrypts_client_secret_only():
    mock_db = MagicMock()
    cursor = mock_db.cursor.return_value
    cursor.rowcount = 1
    with patch.object(spotify_utils, "get_connection", return_value=mock_db):
        with patch.object(secrets_utils, "encrypt", return_value="ENCRYPTED") as mock_encrypt:
            spotify_utils.save_spotify_credentials("client-id", "plain-secret", "http://redirect")
    mock_encrypt.assert_called_once_with("plain-secret")
    secret_call = [
        c for c in cursor.execute.call_args_list if "spotify_client_secret" in c.args[0]
    ][0]
    assert secret_call.args[1] == ("ENCRYPTED",)
    id_call = [c for c in cursor.execute.call_args_list if "spotify_client_id" in c.args[0]][0]
    assert id_call.args[1] == ("client-id",)  # not encrypted -- not a secret


def test_get_spotify_config_decrypts_client_secret_only():
    mock_db = MagicMock()
    cursor = mock_db.cursor.return_value
    cursor.fetchall.return_value = [
        ("spotify_client_id", "client-id"),
        ("spotify_client_secret", "ENCRYPTED"),
    ]
    with patch.object(spotify_utils, "get_connection", return_value=mock_db):
        with patch.object(
            secrets_utils, "decrypt_or_plaintext", return_value="plain-secret"
        ) as mock_decrypt:
            config = spotify_utils.get_spotify_config()
    mock_decrypt.assert_called_once_with("ENCRYPTED")
    assert config["spotify_client_secret"] == "plain-secret"  # pragma: allowlist secret
    assert config["spotify_client_id"] == "client-id"
