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


class _FakeDB:
    """Stands in for the pooled connection: serves the stored last_state and records the UPDATE."""

    def __init__(self, stored_last_state=None):
        self._stored = stored_last_state
        self.updates = []
        self.committed = False
        self.closed = False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        if sql.lstrip().upper().startswith("UPDATE"):
            self.updates.append((sql, params))

    def fetchone(self):
        return (self._stored,) if self._stored is not None else None

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _entity(state, **attributes):
    return {
        "entity_id": "switch.lamp",
        "state": state,
        "last_changed": "2026-11-02T05:00:00+00:00",
        "attributes": {"friendly_name": "Lamp", **attributes},
    }


def _stored(state, **attributes):
    return ha_utils.orjson.dumps(
        {
            "entity_id": "switch.lamp",
            "state": state,
            "attributes": {"friendly_name": "Lamp", **attributes},
        }
    ).decode()


def _patch(monkeypatch, db, reads):
    reads = iter(reads)
    monkeypatch.setattr(ha_utils, "get_ha_device_state", lambda entity_id: next(reads))
    monkeypatch.setattr(ha_utils, "get_connection", lambda: db)
    monkeypatch.setattr(ha_utils.time, "sleep", lambda s: None)


def test_state_to_device_matches_the_synced_last_state_shape():
    """The refresh and the 15-minute sync must write the same last_state shape, or clients see
    fields appear and disappear depending on which ran last."""
    device = ha_utils._state_to_device(_entity("on", brightness=200))
    assert device["domain"] == "switch"
    assert device["name"] == "Lamp"
    assert device["state"] == "on"
    assert device["brightness"] == 200
    assert device["mac_address"] is None
    with_mac = _entity("on", connections=[["mac", "aa:bb:cc:dd:ee:ff"]])
    assert ha_utils._state_to_device(with_mac)["mac_address"] == "AA:BB:CC:DD:EE:FF"


def test_refresh_waits_for_ha_to_report_the_commanded_state(monkeypatch):
    """Cloud integrations (Tuya) ack the service call before the entity flips, so one immediate
    read would persist the stale pre-command state -- the very bug being fixed."""
    db = _FakeDB()
    _patch(monkeypatch, db, [_entity("on"), _entity("on"), _entity("off")])

    assert ha_utils.refresh_ha_device_state("switch.lamp", "turn_off") is True

    ((sql, params),) = db.updates
    assert "UPDATE smarthome_devices" in sql
    assert '"state":"off"' in params[0]
    assert params[1] is True and params[2] == "switch.lamp"
    assert db.committed and db.closed


def test_refresh_returns_immediately_when_already_in_the_commanded_state(monkeypatch):
    """turn_on on a lamp that is already on must not sit out the whole timeout."""
    db = _FakeDB()
    _patch(monkeypatch, db, [_entity("on")])  # a second read would raise StopIteration
    assert ha_utils.refresh_ha_device_state("switch.lamp", "turn_on") is True


def test_refresh_without_a_target_state_waits_for_a_change_from_whats_stored(monkeypatch):
    """toggle/set_brightness have no fixed target: wait until state or attributes differ from the
    stored row, rather than persisting HA's not-yet-updated reading."""
    db = _FakeDB(_stored("on", brightness=10))
    _patch(
        monkeypatch,
        db,
        [_entity("on", brightness=10), _entity("on", brightness=10), _entity("on", brightness=200)],
    )

    assert ha_utils.refresh_ha_device_state("switch.lamp", "set_brightness") is True
    assert '"brightness":200' in db.updates[0][1][0]


def test_refresh_persists_immediately_when_stored_state_is_already_stale(monkeypatch):
    """If the row is stale and HA already differs from it, there is nothing to wait for."""
    db = _FakeDB(_stored("on"))
    _patch(monkeypatch, db, [_entity("off")])
    assert ha_utils.refresh_ha_device_state("switch.lamp", "toggle") is True
    assert '"state":"off"' in db.updates[0][1][0]


def test_refresh_gives_up_at_the_timeout_and_persists_the_latest_read(monkeypatch):
    db = _FakeDB()
    clock = iter(range(0, 100))
    monkeypatch.setattr(ha_utils, "get_ha_device_state", lambda entity_id: _entity("on"))
    monkeypatch.setattr(ha_utils, "get_connection", lambda: db)
    monkeypatch.setattr(ha_utils.time, "sleep", lambda s: None)
    monkeypatch.setattr(ha_utils.time, "monotonic", lambda: next(clock))

    assert ha_utils.refresh_ha_device_state("switch.lamp", "turn_off", timeout=3) is True
    assert '"state":"on"' in db.updates[0][1][0]


def test_refresh_never_raises_when_ha_is_unreachable(monkeypatch):
    """The control already succeeded; a failed refresh must not turn it into a 500."""
    db = _FakeDB()
    monkeypatch.setattr(ha_utils, "get_connection", lambda: db)
    monkeypatch.setattr(ha_utils, "get_ha_device_state", lambda entity_id: None)
    assert ha_utils.refresh_ha_device_state("switch.lamp", "turn_off") is False
    assert db.updates == [] and db.closed

    def boom(entity_id):
        raise RuntimeError("network down")

    monkeypatch.setattr(ha_utils, "get_ha_device_state", boom)
    assert ha_utils.refresh_ha_device_state("switch.lamp", "turn_off") is False
