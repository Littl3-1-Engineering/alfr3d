import importlib
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import common

# service_user connects to Kafka and reads its DB env at import time; stub both.
for _name in (
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PSWD",
    "MYSQL_NAME",
    "ALFR3D_ENV_NAME",
):
    os.environ.setdefault(_name, "test")
with patch.object(common, "get_producer", return_value=MagicMock()), patch.object(
    common, "get_kafka_url", return_value="kafka:9092"
):
    user_app = importlib.import_module("services.service_user.app")

STAT = {"online": 1, "offline": 2}


def _user(username, state):
    # Column order mirrors `SELECT * FROM user` as used by update_user_state().
    return (
        7,
        username,
        None,
        None,
        None,
        state,
        datetime.now(timezone.utc).replace(tzinfo=None),
        None,
        3,
    )


def _run(username):
    cursor = MagicMock()
    cursor.fetchone.return_value = (3, "resident")
    producer = MagicMock()
    with patch.object(user_app, "check_mute", return_value=False), patch.object(
        user_app, "speak_welcome"
    ) as welcome:
        user_app.update_user_state(
            _user(username, STAT["offline"]),
            cursor,
            MagicMock(),
            STAT,
            producer,
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
        )
    return cursor, producer, welcome


def test_alfr3d_self_is_not_greeted():
    cursor, producer, welcome = _run("alfr3d")

    welcome.assert_not_called()
    assert not [c for c in producer.send.call_args_list if c.args[0] == "speak"]
    # The state row and the event-stream entry still update for the alfr3d user.
    assert any("SET state" in str(c.args[0]) for c in cursor.execute.call_args_list)
    assert [c for c in producer.send.call_args_list if c.args[0] == "event-stream"]


def test_household_member_is_still_greeted():
    _, producer, welcome = _run("athos")

    welcome.assert_called_once()
    assert [c for c in producer.send.call_args_list if c.args[0] == "speak"]
