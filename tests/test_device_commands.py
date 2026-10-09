"""Unit tests for services/common/device_commands.py and the senders that call it.

Every device command ALFR3D sends is recorded in device_command_history (migration 044) by the
three low-level senders. These tests check what gets recorded and that recording can never
break device control. The DB write itself is stubbed by conftest's autouse
`_no_device_command_db_writes` fixture, which collects (sql, args) tuples.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import orjson

from common import device_commands, esphome_utils, ha_utils, st_utils

# Positions in record_device_command()'s INSERT args tuple.
_SOURCE, _ENTITY_REF, _COMMAND, _REQUESTED, _PARAMS, _SUCCESS, _MESSAGE = 2, 3, 4, 5, 6, 7, 8
_ORIGIN, _USER_ID, _CONTEXT = 9, 10, 11


def test_record_device_command_writes_full_row(_no_device_command_db_writes):
    device_commands.record_device_command(
        source="homeassistant",
        entity_ref="light.living_room",
        command="turn_on",
        params={"brightness_pct": 30},
        success=True,
        message="Command sent",
        origin="user",
        user_id=1,
        requested_command="set_brightness",
        context={"endpoint": "device_control", "device_id": 7},
    )

    assert len(_no_device_command_db_writes) == 1
    sql, args = _no_device_command_db_writes[0]
    assert "INSERT INTO device_command_history" in sql
    assert "ha_entity_id = %s" in sql
    assert args[0:2] == ("homeassistant", "light.living_room")
    assert args[_SOURCE] == "homeassistant"
    assert args[_COMMAND] == "turn_on"
    assert args[_REQUESTED] == "set_brightness"
    assert orjson.loads(args[_PARAMS]) == {"brightness_pct": 30}
    assert args[_SUCCESS] is True
    assert args[_ORIGIN] == "user"
    assert args[_USER_ID] == 1
    assert orjson.loads(args[_CONTEXT]) == {"endpoint": "device_control", "device_id": 7}


def test_record_device_command_resolves_device_by_source_column(_no_device_command_db_writes):
    device_commands.record_device_command(
        source="esphome", entity_ref="node.local:3", command="turn_off", success=True
    )
    device_commands.record_device_command(
        source="smartthings", entity_ref="abc-123", command="switch.off", success=True
    )

    assert "esp_entity_id = %s" in _no_device_command_db_writes[0][0]
    assert "st_device_id = %s" in _no_device_command_db_writes[1][0]


def test_record_device_command_unknown_origin_becomes_system(_no_device_command_db_writes):
    device_commands.record_device_command(
        source="homeassistant", entity_ref="switch.x", command="toggle", success=False, origin="?"
    )

    assert _no_device_command_db_writes[0][1][_ORIGIN] == "system"
    assert _no_device_command_db_writes[0][1][_SUCCESS] is False


def test_record_device_command_never_raises(monkeypatch):
    def boom(sql, args):
        raise RuntimeError("Table 'device_command_history' doesn't exist")

    monkeypatch.setattr(device_commands, "_insert", boom)

    device_commands.record_device_command(
        source="homeassistant", entity_ref="light.x", command="turn_on", success=True
    )


def test_ha_control_device_records_success_and_attribution(_no_device_command_db_writes):
    response = MagicMock(status_code=200)
    with patch.object(
        ha_utils, "get_ha_config", return_value={"ha_url": "http://ha", "ha_token": "t"}
    ), patch.object(ha_utils.requests, "post", return_value=response):
        ok, _ = ha_utils.ha_control_device(
            "media_player.tv",
            "volume_set",
            {"volume_level": 0.4},
            origin="user",
            user_id=2,
            requested_command="volume_set",
        )

    assert ok is True
    args = _no_device_command_db_writes[0][1]
    assert args[_ENTITY_REF] == "media_player.tv"
    assert args[_COMMAND] == "volume_set"
    assert orjson.loads(args[_PARAMS]) == {"volume_level": 0.4}
    assert args[_ORIGIN] == "user"
    assert args[_USER_ID] == 2


def test_ha_control_device_records_failures_too(_no_device_command_db_writes):
    response = MagicMock(status_code=500, text="boom")
    with patch.object(
        ha_utils, "get_ha_config", return_value={"ha_url": "http://ha", "ha_token": "t"}
    ), patch.object(ha_utils.requests, "post", return_value=response):
        ok, message = ha_utils.ha_control_device("light.x", "turn_on")

    assert ok is False
    args = _no_device_command_db_writes[0][1]
    assert args[_SUCCESS] is False
    assert args[_MESSAGE] == message
    assert args[_ORIGIN] == "system"


def test_st_control_device_records_capability_dot_command(_no_device_command_db_writes):
    response = MagicMock(status_code=200)
    with patch.object(st_utils, "get_st_config", return_value={"st_pat": "p"}), patch.object(
        st_utils.requests, "post", return_value=response
    ):
        st_utils.st_control_device("dev-1", "switchLevel", "setLevel", [40], origin="user")

    args = _no_device_command_db_writes[0][1]
    assert args[_COMMAND] == "switchLevel.setLevel"
    assert orjson.loads(args[_PARAMS]) == [40]


def test_esphome_control_records_host_key_entity_ref(_no_device_command_db_writes):
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = ("192.168.1.50", 6053, None)
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()

    with patch.object(esphome_utils, "get_connection", return_value=mock_db), patch.object(
        esphome_utils, "APIClient", return_value=mock_client
    ):
        ok, _ = asyncio.run(
            esphome_utils.control_esphome_device_async(
                "node.local", 3, "light", "set_brightness", {"brightness": 30}, origin="routine"
            )
        )

    assert ok is True
    args = _no_device_command_db_writes[0][1]
    assert args[_ENTITY_REF] == "node.local:3"
    assert args[_COMMAND] == "set_brightness"
    assert args[_ORIGIN] == "routine"


def test_daemon_routine_device_action_is_attributed_to_the_routine():
    from service_daemon.utils import util_routines

    with patch.object(util_routines, "MySQLdb") as mock_mysql, patch.object(
        util_routines.ha_utils, "ha_control_device", return_value=(True, "Command sent")
    ) as mock_control:
        mock_mysql.connect.return_value.cursor.return_value.fetchone.return_value = (
            "homeassistant",
            "lock.front_door",
        )
        util_routines.control_iot_device(
            5,
            "lock",
            {},
            command_attribution={
                "origin": "routine",
                "requested_command": "lock",
                "context": {"routine_id": 9, "trigger": "scheduled"},
            },
        )

    kwargs = mock_control.call_args.kwargs
    assert kwargs["origin"] == "routine"
    assert kwargs["context"] == {"routine_id": 9, "trigger": "scheduled"}
