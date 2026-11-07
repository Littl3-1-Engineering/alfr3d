"""sync_ha_devices: renames re-point the existing row, removed entities are pruned.

HA's entity_id changes when an entity is renamed. The sync used to key rows by entity_id alone and
never delete, so a rename left an "online" ghost row (frozen state, commands that silently hit
nothing) next to a new row -- and anything pinned on the ghost (Quick Controls) never worked again.
"""

from common import ha_utils


class _FakeDB:
    """Just enough of a cursor to run sync_ha_devices against an in-memory smarthome_devices."""

    def __init__(self, rows):
        # rows: id -> dict(entity_id, domain, mac, ha_device_id, name)
        self.rows = {r["id"]: dict(r) for r in rows}
        self.next_id = max(self.rows, default=0) + 1
        self._result = []
        self.committed = False

    def cursor(self):
        return self

    def close(self):
        pass

    def commit(self):
        self.committed = True

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self._result = []
        if s.startswith("SELECT id FROM environment"):
            self._result = [(1,)]
        elif s.startswith("SELECT id, ha_entity_id, device_type"):
            self._result = [
                (i, r["entity_id"], r["domain"], r["mac"], r["ha_device_id"])
                for i, r in self.rows.items()
            ]
        elif s.startswith("SELECT id FROM device WHERE"):
            self._result = []
        elif s.startswith("SELECT id FROM smarthome_devices WHERE source"):
            self._result = [(i,) for i, r in self.rows.items() if r["entity_id"] == params[0]]
        elif s.startswith("UPDATE smarthome_devices SET ha_entity_id"):
            self.rows[params[1]]["entity_id"] = params[0]
        elif s.startswith("UPDATE smarthome_devices SET name"):
            name, mac, dev, dtype, _online, _state, _link, row_id = params
            row = self.rows[row_id]
            row["name"] = name
            row["mac"] = mac or row["mac"]
            row["ha_device_id"] = dev or row["ha_device_id"]
        elif s.startswith("INSERT INTO smarthome_devices"):
            name, entity, mac, dev, dtype = params[:5]
            self.rows[self.next_id] = {
                "id": self.next_id, "entity_id": entity, "domain": dtype,
                "mac": mac, "ha_device_id": dev, "name": name,
            }  # fmt: skip
            self.next_id += 1
        elif s.startswith("DELETE FROM smarthome_devices"):
            self.rows.pop(params[0], None)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected SQL: {s}")


def _row(i, entity, domain="switch", mac=None, dev=None):
    return {
        "id": i,
        "entity_id": entity,
        "domain": domain,
        "mac": mac,
        "ha_device_id": dev,
        "name": entity,
    }


def _live(entity, domain="switch"):
    return {
        "entity_id": entity, "name": entity, "state": "on", "domain": domain,
        "last_changed": None, "attributes": {}, "mac_address": None,
    }  # fmt: skip


def _run(monkeypatch, db, live, registry=None):
    monkeypatch.setattr(ha_utils, "is_ha_configured", lambda: True)
    monkeypatch.setattr(ha_utils, "get_ha_devices", lambda: [dict(d) for d in live])
    monkeypatch.setattr(ha_utils, "get_ha_registry_info", lambda: registry or {})
    monkeypatch.setattr(ha_utils, "get_connection", lambda: db)
    assert ha_utils.sync_ha_devices() is True


def test_rename_repoints_the_existing_row_and_keeps_its_id(monkeypatch):
    """The row a user pinned must survive the rename -- same id, new entity_id."""
    db = _FakeDB([_row(1, "switch.lamp", dev="dev-a"), _row(2, "switch.other", dev="dev-b")])
    live = [_live("switch.living_room_lamp"), _live("switch.other")]
    reg = {"switch.living_room_lamp": {"device_id": "dev-a", "mac": None},
           "switch.other": {"device_id": "dev-b", "mac": None}}  # fmt: skip
    _run(monkeypatch, db, live, reg)

    assert db.rows[1]["entity_id"] == "switch.living_room_lamp"
    assert set(db.rows) == {1, 2}  # no duplicate inserted, nothing pruned


def test_rename_is_matched_by_mac(monkeypatch):
    db = _FakeDB([_row(1, "switch.old", mac="AA:BB:CC:DD:EE:FF"), _row(2, "switch.keep")])
    live = [_live("switch.new"), _live("switch.keep")]
    reg = {"switch.new": {"device_id": None, "mac": "AA:BB:CC:DD:EE:FF"}}
    _run(monkeypatch, db, live, reg)
    assert db.rows[1]["entity_id"] == "switch.new"
    assert len(db.rows) == 2


def test_entity_removed_from_ha_is_removed_from_alfr3d(monkeypatch):
    db = _FakeDB([_row(i, f"switch.s{i}") for i in range(1, 6)] + [_row(6, "switch.gone")])
    live = [_live(f"switch.s{i}") for i in range(1, 6)]
    _run(monkeypatch, db, live)
    assert "switch.gone" not in {r["entity_id"] for r in db.rows.values()}
    assert len(db.rows) == 5


def test_ambiguous_rename_is_not_guessed(monkeypatch):
    """Two stale switches on one HA device and one new switch: can't tell which it replaced, so
    the stale rows are pruned and the new entity inserted rather than re-pointing the wrong row."""
    rows = [_row(1, "switch.a", dev="d"), _row(2, "switch.b", dev="d")] + [
        _row(i, f"switch.k{i}") for i in range(3, 9)
    ]
    live = [_live("switch.c")] + [_live(f"switch.k{i}") for i in range(3, 9)]
    db = _FakeDB(rows)
    _run(monkeypatch, db, live, {"switch.c": {"device_id": "d", "mac": None}})
    entities = {r["entity_id"] for r in db.rows.values()}
    assert "switch.c" in entities and not {"switch.a", "switch.b"} & entities


def test_a_sync_that_would_remove_most_devices_prunes_nothing(monkeypatch):
    """HA mid-reload reports a fraction of the house; that must not wipe the table."""
    db = _FakeDB([_row(i, f"switch.s{i}") for i in range(1, 7)])
    _run(monkeypatch, db, [_live("switch.s1")])
    assert len(db.rows) == 6


def test_rename_does_not_touch_a_device_of_a_different_domain(monkeypatch):
    db = _FakeDB(
        [_row(1, "light.x", domain="light", dev="d")]
        + [_row(i, f"switch.k{i}") for i in range(2, 8)]
    )
    live = [_live("switch.new")] + [_live(f"switch.k{i}") for i in range(2, 8)]
    _run(monkeypatch, db, live, {"switch.new": {"device_id": "d", "mac": None}})
    assert "light.x" not in {r["entity_id"] for r in db.rows.values()}  # pruned, not re-pointed
    assert any(r["entity_id"] == "switch.new" for r in db.rows.values())


class _Resp:
    def __init__(self, code, text="[]"):
        self.status_code, self.text = code, text


def _cfg(monkeypatch):
    monkeypatch.setattr(ha_utils, "get_ha_config", lambda: {"ha_url": "http://ha", "ha_token": "t"})


def test_entity_exists_distinguishes_missing_from_unreachable(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setattr(ha_utils.requests, "get", lambda *a, **k: _Resp(404))
    assert ha_utils.ha_entity_exists("switch.x") is False
    monkeypatch.setattr(ha_utils.requests, "get", lambda *a, **k: _Resp(200))
    assert ha_utils.ha_entity_exists("switch.x") is True

    def boom(*a, **k):
        raise ha_utils.requests.ConnectionError("down")

    monkeypatch.setattr(ha_utils.requests, "get", boom)
    assert ha_utils.ha_entity_exists("switch.x") is None


def test_registry_info_extracts_device_id_and_mac(monkeypatch):
    _cfg(monkeypatch)
    body = (
        '[{"e":"switch.a","d":"dev1","c":[["mac","aa:bb:cc:dd:ee:ff"]]},'
        '{"e":"switch.b","d":null,"c":[]}]'
    )
    monkeypatch.setattr(ha_utils.requests, "post", lambda *a, **k: _Resp(200, body))
    info = ha_utils.get_ha_registry_info()
    assert info["switch.a"] == {"device_id": "dev1", "mac": "AA:BB:CC:DD:EE:FF"}
    assert info["switch.b"] == {"device_id": None, "mac": None}


def test_registry_info_failure_falls_back_to_empty(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setattr(ha_utils.requests, "post", lambda *a, **k: _Resp(500))
    assert ha_utils.get_ha_registry_info() == {}
