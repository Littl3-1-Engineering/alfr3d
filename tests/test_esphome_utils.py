"""Unit tests for services/common/esphome_utils.py.

Unlike the integration-style tests elsewhere in this directory (driven against real MySQL/Kafka,
auto-skipped when that infra isn't reachable -- see conftest.py's docstring), these mock the DB
connection and the aioesphomeapi client directly. The riskiest logic here is pure command-mapping
(fan speed strings -> FanSpeed enum, entity class name -> ALFR3D device_type) that doesn't need a
live device or database to verify.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

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


# --- Generic control command param scaling -----------------------------------------------
# ControlBlade.jsx's brightness/volume sliders send 0-100 (percent) -- aioesphomeapi's
# light_command/media_player_command take normalized 0.0-1.0 floats, matching the pattern
# cover_command's `position` already used. A prior version of this code divided brightness by
# 255 (HA's raw-brightness convention) and left volume unscaled entirely, so both silently sent
# the wrong value to real devices.


def _mock_accepted_node_db():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = ("192.168.1.50", 6053, None)
    return mock_db


def test_control_esphome_device_async_scales_brightness_percent_to_normalized_float():
    import asyncio

    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()

    with patch.object(
        esphome_utils, "get_connection", return_value=_mock_accepted_node_db()
    ), patch.object(esphome_utils, "APIClient", return_value=mock_client):
        success, message = asyncio.run(
            esphome_utils.control_esphome_device_async(
                "livingroom.local", 1, "light", "set_brightness", {"brightness": 75}
            )
        )

    assert success is True
    mock_client.light_command.assert_called_once_with(key=1, state=True, brightness=0.75)


def test_control_esphome_device_async_scales_volume_percent_to_normalized_float():
    import asyncio

    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()

    with patch.object(
        esphome_utils, "get_connection", return_value=_mock_accepted_node_db()
    ), patch.object(esphome_utils, "APIClient", return_value=mock_client):
        success, message = asyncio.run(
            esphome_utils.control_esphome_device_async(
                "livingroom.local", 2, "media_player", "volume_set", {"volume": 40}
            )
        )

    assert success is True
    mock_client.media_player_command.assert_called_once_with(key=2, volume=0.4)


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


# --- Push (persistent, Phase 5) --------------------------------------------------------------


def test_handle_state_push_updates_known_entity():
    mock_entity = MagicMock()
    mock_entity.object_id = "temperature"
    mock_entity.key = 42
    mock_state = MagicMock()
    mock_state.key = 42
    mock_state.to_dict.return_value = {"state": 21.5}
    entity_map = {42: mock_entity}

    mock_db = MagicMock()
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        esphome_utils._handle_state_push("kitchen.local", entity_map, mock_state)

    cursor = mock_db.cursor.return_value
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert "UPDATE smarthome_devices" in sql
    assert "online = TRUE" in sql
    assert params[1] == "kitchen.local:42"
    mock_db.commit.assert_called_once()


def test_handle_state_push_noops_for_unknown_entity_key():
    """A state push for a key this connection never saw in list_entities_services() (e.g. a
    race on reconnect) must not write a garbage row -- silently drop it instead."""
    mock_state = MagicMock()
    mock_state.key = 999
    mock_db = MagicMock()
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        esphome_utils._handle_state_push("kitchen.local", {}, mock_state)

    mock_db.cursor.return_value.execute.assert_not_called()


def test_mark_node_entities_offline_scopes_to_hostname_prefix():
    mock_db = MagicMock()
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        esphome_utils._mark_node_entities_offline("kitchen.local")

    cursor = mock_db.cursor.return_value
    sql, params = cursor.execute.call_args.args
    assert "online = FALSE" in sql
    assert params == ("kitchen.local:%",)
    mock_db.commit.assert_called_once()


def test_get_node_psk_decrypts_stored_value():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = ("encrypted-blob",)
    with patch.object(esphome_utils, "get_connection", return_value=mock_db), patch.object(
        esphome_utils.secrets_utils, "decrypt_or_plaintext", return_value="realpsk"
    ) as mock_decrypt:
        psk = esphome_utils._get_node_psk("kitchen.local")

    mock_decrypt.assert_called_once_with("encrypted-blob")
    assert psk == "realpsk"


def test_get_node_psk_returns_none_when_node_has_none():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = (None,)
    with patch.object(esphome_utils, "get_connection", return_value=mock_db):
        assert esphome_utils._get_node_psk("kitchen.local") is None


def test_run_push_state_loop_noops_immediately_when_disabled():
    stop_event = threading.Event()
    with patch.object(esphome_utils, "is_esphome_enabled", return_value=False), patch.object(
        esphome_utils, "get_esphome_nodes"
    ) as mock_get_nodes:
        asyncio.run(esphome_utils.run_push_state_loop(stop_event))
    mock_get_nodes.assert_not_called()


def test_run_push_state_loop_starts_one_task_per_accepted_node_and_cancels_on_stop():
    """Doesn't exercise a real connection (that's _run_node_push_connection's own concern) --
    verifies the orchestration loop starts a task per accepted node with the right args, then
    tears every task down cleanly once stop_event is set, rather than leaking tasks."""
    stop_event = threading.Event()
    started_with = []

    async def fake_connection(hostname, ip_address, port, psk, stop_event_arg):
        started_with.append((hostname, ip_address, port, psk))
        try:
            await asyncio.sleep(1000)
        except asyncio.CancelledError:
            raise

    real_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        # Stand-in for the loop's _NODE_POLL_INTERVAL wait: yield control once so the
        # just-created connection task actually gets to run its first line, then end the loop
        # on the next check.
        await real_sleep(0)
        stop_event.set()

    with patch.object(esphome_utils, "is_esphome_enabled", return_value=True), patch.object(
        esphome_utils,
        "get_esphome_nodes",
        return_value=[{"hostname": "kitchen.local", "ip_address": "10.0.0.5", "port": 6053}],
    ), patch.object(esphome_utils, "_get_node_psk", return_value=None), patch.object(
        esphome_utils, "_run_node_push_connection", side_effect=fake_connection
    ), patch(
        "asyncio.sleep", side_effect=fake_sleep
    ):
        asyncio.run(esphome_utils.run_push_state_loop(stop_event))

    assert started_with == [("kitchen.local", "10.0.0.5", 6053, None)]
