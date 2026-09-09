"""Unit tests for services/common/ha_utils.py.

Only covers translate_generic_control_params for now -- the pure command-mapping logic that
bridges ControlBlade.jsx's provider-agnostic command vocabulary onto Home Assistant's actual REST
service-call conventions. See todo/todo_iot_central_control.md: a prior version of this mapping
passed ControlBlade's params straight through, which silently sent HA the wrong value for
brightness, volume, and fan speed (right endpoint, wrong payload).
"""

from common import ha_utils


def test_set_brightness_converts_percent_to_brightness_pct():
    """ControlBlade's slider sends 0-100; HA's bare `brightness` field is raw 0-255, so passing
    it straight through would under-light the bulb. `brightness_pct` is the field HA expects for
    a 0-100 percent value."""
    assert ha_utils.translate_generic_control_params("set_brightness", {"brightness": 75}) == {
        "brightness_pct": 75
    }


def test_volume_set_converts_percent_to_volume_level_float():
    """HA's media_player.volume_set service expects volume_level as a 0.0-1.0 float, not the
    0-100 percent ControlBlade's slider produces -- mirrors audio_cast.py's
    set_speaker_volume, the known-working reference for this same HA service call."""
    assert ha_utils.translate_generic_control_params("volume_set", {"volume": 40}) == {
        "volume_level": 0.4
    }


def test_set_speed_converts_named_speed_to_percentage():
    """HA's fan.set_percentage service takes a numeric `percentage`, not the
    off/low/medium/high name ControlBlade's speed buttons send."""
    assert ha_utils.translate_generic_control_params("set_speed", {"speed": "medium"}) == {
        "percentage": 66
    }


def test_set_speed_defaults_unknown_speed_to_zero():
    assert ha_utils.translate_generic_control_params("set_speed", {"speed": "turbo"}) == {
        "percentage": 0
    }


def test_other_commands_pass_params_through_unchanged():
    """set_temperature and set_position already match HA's field names 1:1 (temperature,
    position) -- no translation needed."""
    assert ha_utils.translate_generic_control_params("set_temperature", {"temperature": 72}) == {
        "temperature": 72
    }
    assert ha_utils.translate_generic_control_params("set_position", {"position": 50}) == {
        "position": 50
    }


def test_handles_missing_or_none_params():
    assert ha_utils.translate_generic_control_params("turn_on", None) == {}
    assert ha_utils.translate_generic_control_params("volume_set", {}) == {}


def test_ha_state_is_online_treats_any_real_state_as_reachable():
    """sync_ha_devices used `online = state == "on"`, which marked every reachable
    device that wasn't a lit bulb (a media_player on `idle`/`paused`, a switched-off
    light, a `locked` lock, a climate on `heat`) as offline -- and the launcher hides
    offline devices entirely. "online" means HA can talk to the device, i.e. the state
    isn't `unavailable`/`unknown`."""
    for reachable in ("on", "off", "idle", "playing", "paused", "locked", "heat", "23.5"):
        assert ha_utils.ha_state_is_online(reachable) is True, reachable
    for unreachable in ("unavailable", "unknown", None, ""):
        assert ha_utils.ha_state_is_online(unreachable) is False, repr(unreachable)
