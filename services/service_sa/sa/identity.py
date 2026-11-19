"""Stable identity for a sensor (Timeline "Context learning 2/5").

A `smarthome_devices` row id is not an identity. A sensor that is power-cycled or re-adopted gets
new row ids (observed for the ESPHome node on 2026-10-10: ids 37885-37889 retired, 37890-37897
live), and anything keyed on the row id loses its history at that moment. The lake already names a
sensor by what it IS (silver's `sensor_identity` view, plus `sa_sensor_aliases` for retired ids).
This module is that one rule in Python, so the live path resolves a sensor the same way:

    esphome   <host>:<name>            e.g. athom-tem-hum-sensor-4a4734.local:Temperature
    other     <source>:<ha id | st id | name>

`history_ids` returns EVERY row id that has ever held a sensor's readings (its current rows plus
the aliased retired ones), so a query for "the last N hours of this sensor" does not stop at a
power cycle.
"""


def sensor_key(source, name, esp_entity_id=None, ha_entity_id=None, st_device_id=None):
    """The stable key of a `smarthome_devices` row, identical to silver's sensor_identity rule."""
    if source == "esphome":
        host = (esp_entity_id or "").split(":", 1)[0]
        return f"{host}:{name}"
    return f"{source}:{ha_entity_id or st_device_id or name}"


def history_ids(cursor, key):
    """Every smarthome_devices id whose readings belong to the sensor named `key` (without the
    `esphome:` series prefix): the rows that map to it now, plus ids retired into
    `sa_sensor_aliases`. Sorted, never empty if the sensor exists."""
    cursor.execute(
        "SELECT id FROM smarthome_devices WHERE source = 'esphome' "
        "AND CONCAT(SUBSTRING_INDEX(esp_entity_id, ':', 1), ':', name) = %s",
        (key,),
    )
    ids = {row[0] for row in cursor.fetchall()}
    cursor.execute(
        "SELECT smarthome_device_id FROM sa_sensor_aliases WHERE sensor_key = %s", (key,)
    )
    ids |= {row[0] for row in cursor.fetchall()}
    return sorted(ids)


def esphome_climate_ids(cursor):
    """{"temperature": [ids], "humidity": [ids]} for the household's ESPHome climate node, each
    spanning every row id the sensor has had. With several nodes the newest one (highest current
    id) wins, as the single `climate` snapshot describes one node."""
    cursor.execute(
        "SELECT id, name, esp_entity_id FROM smarthome_devices WHERE source = 'esphome' AND "
        "device_type = 'sensor' AND (LOWER(name) LIKE '%%temperature%%' "
        "OR LOWER(name) LIKE '%%humidity%%') ORDER BY id"
    )
    newest = {}
    for row_id, name, esp_entity_id in cursor.fetchall():
        kind = "temperature" if "temperature" in name.lower() else "humidity"
        newest[kind] = sensor_key("esphome", name, esp_entity_id)
    return {kind: history_ids(cursor, key) for kind, key in newest.items()}
