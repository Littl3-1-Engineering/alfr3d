"""Durable log of every smart-home device command, for SA learning (migration 044).

Every command ALFR3D sends to a device goes through one of three low-level senders --
ha_utils.ha_control_device(), st_utils.st_control_device(),
esphome_utils.control_esphome_device_async() -- and each of them calls record_device_command()
after the send returns. That keeps the log complete for every caller (API endpoints, routines,
audio casting) without each caller having to remember to write it.

Unlike the household_events row the API also emits, this keeps what learning needs: the exact
command, its parameters (brightness 30, volume 0.4, setpoint 21), success or failure, and who or
what issued it (`origin`: "user" | "routine" | "system", plus `user_id` and free-form `context`).

Best-effort: a failure here is logged and swallowed. It must never affect device control.
"""

import logging
from datetime import datetime, timezone

import orjson

from .db_pool import get_connection

logger = logging.getLogger(__name__)

ORIGINS = ("user", "routine", "system")

# smarthome_devices column that identifies a device for each source -- used to resolve
# smarthome_device_id at write time.
_ENTITY_REF_COLUMN = {
    "homeassistant": "ha_entity_id",
    "smartthings": "st_device_id",
    "esphome": "esp_entity_id",
}


def record_device_command(
    *,
    source,
    entity_ref,
    command,
    params=None,
    success,
    message=None,
    origin="system",
    user_id=None,
    requested_command=None,
    context=None,
):
    """Insert one row into device_command_history. Never raises.

    `entity_ref` is the source's own id (HA entity_id, ST device id, ESPHome "host:key");
    `smarthome_device_id` is resolved from it when the device is known, and left NULL otherwise.
    """
    try:
        if origin not in ORIGINS:
            origin = "system"
        ref_column = _ENTITY_REF_COLUMN.get(source)
        if ref_column is None:
            logger.warning(f"Unknown device command source '{source}', not recorded")
            return
        issued_at = datetime.now(timezone.utc).replace(tzinfo=None)
        _insert(
            "INSERT INTO device_command_history (smarthome_device_id, source, entity_ref, "
            "command, requested_command, params, success, message, origin, user_id, "
            "context, issued_at) VALUES ("
            f"(SELECT id FROM smarthome_devices WHERE source = %s AND {ref_column} = %s "
            "ORDER BY id LIMIT 1), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                source,
                entity_ref,
                source,
                str(entity_ref)[:128],
                str(command)[:64],
                str(requested_command)[:64] if requested_command else None,
                orjson.dumps(params).decode() if params is not None else None,
                bool(success),
                str(message)[:255] if message is not None else None,
                origin,
                user_id,
                orjson.dumps(context).decode() if context is not None else None,
                issued_at,
            ),
        )
    except Exception as e:  # noqa: BLE001 -- logging must never break device control
        logger.error(f"Failed to record device command ({source} {entity_ref} {command}): {e}")


def _insert(sql, args):
    """The only DB write in this module; unit tests stub it (tests/conftest.py)."""
    db = get_connection()
    try:
        cursor = db.cursor()
        cursor.execute(sql, args)
        db.commit()
    finally:
        db.close()
