"""Unit tests for services/common/st_utils.py.

Covers normalize_st_device_type and translate_generic_control_params -- the pure mapping logic
that lets SmartThings devices work through the same unified control endpoint HA/ESPHome use.
See todo/todo_smartthings_generic_control.md: sync_st_devices() used to store ST's raw
deviceTypeName/typeName label (e.g. "Samsung OCF Switch") instead of ControlBlade.jsx's
light/switch/fan/... vocabulary, and control_iot_device() had no SmartThings branch at all --
every ST device 400'd on every command.
"""

from common import st_utils


def _device(*capability_ids):
    return {"components": [{"id": "main", "capabilities": [{"id": c} for c in capability_ids]}]}


def test_normalize_bare_switch():
    assert st_utils.normalize_st_device_type(_device("switch")) == "switch"


def test_normalize_dimmable_light():
    assert st_utils.normalize_st_device_type(_device("switch", "switchLevel")) == "light"


def test_normalize_color_light():
    assert (
        st_utils.normalize_st_device_type(_device("switch", "switchLevel", "colorControl"))
        == "light"
    )


def test_normalize_lock():
    assert st_utils.normalize_st_device_type(_device("lock")) == "lock"


def test_normalize_thermostat():
    assert (
        st_utils.normalize_st_device_type(_device("thermostatMode", "thermostatHeatingSetpoint"))
        == "climate"
    )


def test_normalize_fan():
    assert st_utils.normalize_st_device_type(_device("switch", "fanSpeed")) == "fan"


def test_normalize_window_shade():
    assert st_utils.normalize_st_device_type(_device("windowShade")) == "cover"


def test_normalize_media_player():
    device_type = st_utils.normalize_st_device_type(_device("mediaPlayback", "audioVolume"))
    assert device_type == "media_player"


def test_normalize_binary_sensor():
    assert st_utils.normalize_st_device_type(_device("contactSensor")) == "binary_sensor"


def test_normalize_sensor():
    assert st_utils.normalize_st_device_type(_device("temperatureMeasurement")) == "sensor"


def test_normalize_unknown_device_falls_back():
    assert st_utils.normalize_st_device_type(_device("bridge")) == "unknown"


def test_switch_turn_on_off():
    assert st_utils.translate_generic_control_params("switch", "turn_on", {}) == (
        "switch",
        "on",
        [],
    )
    assert st_utils.translate_generic_control_params("switch", "turn_off", {}) == (
        "switch",
        "off",
        [],
    )


def test_light_set_brightness_passes_percent_through_as_level():
    """ControlBlade's slider sends 0-100, which is exactly what ST's switchLevel.setLevel
    argument expects -- no percent/raw conversion needed, unlike HA's brightness_pct mapping."""
    assert st_utils.translate_generic_control_params(
        "light", "set_brightness", {"brightness": 75}
    ) == ("switchLevel", "setLevel", [75])


def test_fan_set_speed_maps_named_speed_to_st_fan_level():
    assert st_utils.translate_generic_control_params("fan", "set_speed", {"speed": "medium"}) == (
        "fanSpeed",
        "setFanSpeed",
        [2],
    )


def test_fan_set_speed_defaults_unknown_speed_to_zero():
    assert st_utils.translate_generic_control_params("fan", "set_speed", {"speed": "turbo"}) == (
        "fanSpeed",
        "setFanSpeed",
        [0],
    )


def test_lock_unlock():
    assert st_utils.translate_generic_control_params("lock", "lock", {}) == ("lock", "lock", [])
    assert st_utils.translate_generic_control_params("lock", "unlock", {}) == (
        "lock",
        "unlock",
        [],
    )


def test_climate_set_temperature():
    assert st_utils.translate_generic_control_params(
        "climate", "set_temperature", {"temperature": 72}
    ) == ("thermostatHeatingSetpoint", "setHeatingSetpoint", [72])


def test_climate_turn_on_off_maps_to_thermostat_mode():
    assert st_utils.translate_generic_control_params("climate", "turn_on", {}) == (
        "thermostatMode",
        "setThermostatMode",
        ["auto"],
    )
    assert st_utils.translate_generic_control_params("climate", "turn_off", {}) == (
        "thermostatMode",
        "setThermostatMode",
        ["off"],
    )


def test_cover_turn_on_off_maps_to_open_close():
    assert st_utils.translate_generic_control_params("cover", "turn_on", {}) == (
        "windowShade",
        "open",
        [],
    )
    assert st_utils.translate_generic_control_params("cover", "turn_off", {}) == (
        "windowShade",
        "close",
        [],
    )


def test_cover_set_position():
    assert st_utils.translate_generic_control_params("cover", "set_position", {"position": 40}) == (
        "windowShadeLevel",
        "setShadeLevel",
        [40],
    )


def test_media_player_play_pause_and_volume():
    assert st_utils.translate_generic_control_params("media_player", "media_play", {}) == (
        "mediaPlayback",
        "play",
        [],
    )
    assert st_utils.translate_generic_control_params("media_player", "media_pause", {}) == (
        "mediaPlayback",
        "pause",
        [],
    )
    assert st_utils.translate_generic_control_params(
        "media_player", "volume_set", {"volume": 30}
    ) == ("audioVolume", "setVolume", [30])


def test_unsupported_command_for_device_type_returns_none():
    assert st_utils.translate_generic_control_params("lock", "set_brightness", {}) is None
    assert st_utils.translate_generic_control_params("sensor", "turn_on", {}) is None


def test_handles_missing_or_none_params():
    assert st_utils.translate_generic_control_params("switch", "turn_on", None) == (
        "switch",
        "on",
        [],
    )
    assert st_utils.translate_generic_control_params("light", "set_brightness", None) is None
