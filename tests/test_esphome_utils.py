"""Unit tests for services/common/esphome_utils.py.

Unlike the integration-style tests elsewhere in this directory (driven against real MySQL/Kafka,
auto-skipped when that infra isn't reachable -- see conftest.py's docstring), these mock the DB
connection and the aioesphomeapi client directly. The riskiest logic here is pure command-mapping
(fan speed strings -> FanSpeed enum, entity class name -> ALFR3D device_type) that doesn't need a
live device or database to verify.
"""

from unittest.mock import MagicMock, patch

import pytest
from aioesphomeapi import FanSpeed

from common import esphome_utils


# --- Config -------------------------------------------------------------------------------


def test_is_esphome_enabled_true_by_default_when_missing():
    with patch.object(esphome_utils, "get_esphome_config", return_value={}):
        assert esphome_utils.is_esphome_enabled() is True


def test_is_esphome_enabled_false_when_disabled():
    with patch.object(
        esphome_utils, "get_esphome_config", return_value={"esphome_enabled": "false"}
    ):
        assert esphome_utils.is_esphome_enabled() is False


def test_get_esphome_config_reads_config_table():
    mock_db = MagicMock()
    mock_cursor = mock_db.cursor.return_value
    mock_cursor.fetchall.return_value = [("esphome_enabled", "true")]
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        config = esphome_utils.get_esphome_config()
    assert config == {"esphome_enabled": "true"}
    mock_db.close.assert_called_once()


# --- Fan speed command mapping --------------------------------------------------------------


@pytest.mark.parametrize(
    "speed,expected",
    [
        ("off", {"state": False}),
        ("", {"state": False}),
        ("low", {"state": True, "speed": FanSpeed.LOW}),
        ("medium", {"state": True, "speed": FanSpeed.MEDIUM}),
        ("high", {"state": True, "speed": FanSpeed.HIGH}),
    ],
)
def test_fan_speed_command_matches_controlblade_vocabulary(speed, expected):
    """ControlBlade.jsx sends params.speed as one of off/low/medium/high (see
    renderFanControls in services/service_frontend/src/components/ControlBlade.jsx) --
    this must keep accepting exactly that vocabulary, unchanged, since the frontend isn't
    ESPHome-aware and reuses the same command shape as HA/ST."""
    assert esphome_utils._fan_speed_command({"speed": speed}) == expected


def test_fan_speed_command_defaults_to_off_when_missing():
    assert esphome_utils._fan_speed_command({}) == {"state": False}


# --- Entity domain mapping -------------------------------------------------------------------


def test_entity_domain_map_covers_ha_utils_allowed_domains():
    """ha_utils.get_ha_devices() only surfaces entities in this exact domain set
    (services/common/ha_utils.py) -- ESPHome's per-entity device_type values must line up so
    both sources render identically in DeviceRegistry/Blueprint."""
    expected_domains = {
        "light",
        "switch",
        "fan",
        "climate",
        "cover",
        "lock",
        "media_player",
        "sensor",
        "binary_sensor",
        "camera",
    }
    assert set(esphome_utils._ENTITY_DOMAIN_MAP.values()) == expected_domains


# --- Node bookkeeping -------------------------------------------------------------------------


def test_remove_esphome_node_deletes_node_and_its_entities():
    mock_db = MagicMock()
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        esphome_utils.remove_esphome_node("livingroom.local")

    cursor = mock_db.cursor.return_value
    calls = [c.args[0] for c in cursor.execute.call_args_list]
    assert any("DELETE FROM smarthome_devices" in c for c in calls)
    assert any("DELETE FROM esphome_nodes" in c for c in calls)
    mock_db.commit.assert_called_once()


def test_accept_esphome_node_async_fails_fast_when_node_unknown():
    """Accepting a node that was never discovered (no esphome_nodes row) must not attempt a
    connection at all -- see todo/todo_esphome.md Design section 1's manual-accept requirement."""
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = None

    import asyncio

    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        success, message, device_info = asyncio.run(
            esphome_utils.accept_esphome_node_async("unknown.local")
        )

    assert success is False
    assert "not found" in message.lower()
    assert device_info is None
