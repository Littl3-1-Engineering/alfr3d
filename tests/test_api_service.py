"""Tests for the ALFR3D API service."""

import os
import sys
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_api"))

os.environ.setdefault("MYSQL_DATABASE", "localhost")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PSWD", "testrootpassword")
os.environ.setdefault("MYSQL_NAME", "test_alfr3d_db")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("ALFR3D_ENV_NAME", "test")
os.environ.setdefault(
    "ALFR3D_SECRETS_KEY",
    "8pS1sOe6r8kM2v3z1Q5X0jz3n5aQ6l1V9j0k3m0zQeM=",  # pragma: allowlist secret
)  # fixed test-only Fernet key, not a real credential


@pytest.fixture(scope="session")
def api_app():
    """FastAPI app fixture for API tests."""
    from app import app

    return app


@pytest.fixture(scope="session")
def api_client(api_app):
    """FastAPI TestClient for API tests."""
    return TestClient(api_app)


@pytest.fixture(autouse=True)
def _clear_api_cache():
    """Clear the shared API cache between tests to avoid cross-test contamination."""
    import dependencies as deps

    deps._cache.clear()
    yield


def _mock_connection(mock_db_connection, fetchall_value):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = fetchall_value
    return mock_db


@patch("dependencies.db_connection")
def test_api_health_check(mock_db_connection, api_client):
    """Test API health check endpoint."""
    _mock_connection(mock_db_connection, [])

    response = api_client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@patch("dependencies.db_connection")
def test_api_get_users(mock_db_connection, api_client):
    """Test get users endpoint."""
    _mock_connection(
        mock_db_connection,
        [
            (1, "user1", "email1", "about1", "online", "resident", None, None, "boss"),
            (2, "user2", "email2", "about2", "offline", "guest", None, None, None),
        ],
    )

    response = api_client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "user1"
    assert data[0]["title"] == "boss"
    assert data[1]["title"] is None


@patch("dependencies.db_connection")
def test_api_get_devices(mock_db_connection, api_client):
    """Test get devices endpoint."""
    _mock_connection(
        mock_db_connection,
        [
            (
                1,
                "device1",
                "192.168.1.1",
                "mac1",
                "active",
                "type1",
                "user1",
                None,
                None,
                None,
                None,
            ),
            (
                2,
                "device2",
                "192.168.1.2",
                "mac2",
                "inactive",
                "type2",
                "user2",
                None,
                None,
                None,
                "rtsp://user:pass@10.0.0.5:554/stream1",  # pragma: allowlist secret
            ),
        ],
    )

    response = api_client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "device1"
    assert data[0]["has_stream"] is False
    assert data[1]["has_stream"] is True
    assert "stream_url" not in data[1]


@patch("routes.devices.db_connection")
def test_users_with_devices_includes_title(mock_db_connection, api_client):
    """PersonnelRoster's admin dialog reads this endpoint (not GET /api/users), so `title`
    has to round-trip here too or the "how Alfred addresses them" field can never load."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchall.side_effect = [
        [
            {
                "id": 1,
                "name": "Alice",
                "email": "alice@example.com",
                "about_me": "",
                "title": "boss",
                "state": "online",
                "type": "owner",
                "last_online": None,
                "created_at": None,
            }
        ],
        [],
    ]

    response = api_client.get("/api/users-with-devices")
    assert response.status_code == 200
    data = response.json()
    assert data["users"][0]["title"] == "boss"


def test_api_get_events(api_client):
    """Test get events endpoint."""
    response = api_client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@patch("routes.music.db_connection")
def test_api_get_now_playing_returns_persisted_state(mock_db_connection, api_client):
    """GET /api/music/now-playing returns the daemon's last-persisted config
    row as-is -- a fast local read, no live Spotify call."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (
        '{"track_id": "track1", "title": "Song", "artist": "Artist", '
        '"is_playing": true, "updated_at": "2026-08-17T00:00:00+00:00"}',
    )

    response = api_client.get("/api/music/now-playing")
    assert response.status_code == 200
    data = response.json()
    assert data["track_id"] == "track1"
    assert data["title"] == "Song"
    assert data["is_playing"] is True


@patch("routes.music.db_connection")
def test_api_get_now_playing_defaults_when_nothing_persisted(mock_db_connection, api_client):
    """No config row yet (nothing observed playing since the last restart)
    returns null fields rather than a 404/error."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    response = api_client.get("/api/music/now-playing")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "track_id": None,
        "title": None,
        "artist": None,
        "is_playing": False,
        "updated_at": None,
    }


# --- Auth/RBAC wiring: every write route requires a token + the right role (todo_auth_rbac.md) --


def _bearer(user_id, user_type):
    from auth import jwt_utils

    token = jwt_utils.create_access_token(user_id, user_type)
    return {"Authorization": f"Bearer {token}"}


def test_write_route_rejects_unauthenticated_request(api_client):
    """A resident-allowed write route (POST /api/devices) with no Authorization header at
    all -- proves require_permission's dependency chain runs before the route body, not just
    that individual functions behave correctly in isolation (see test_auth.py for those)."""
    response = api_client.post("/api/devices", json={"name": "lamp", "type": "light"})
    assert response.status_code == 401


def test_write_route_rejects_guest_role_token(api_client):
    """guest == unauthenticated by design -- must 403, not silently succeed."""
    response = api_client.post(
        "/api/devices",
        json={"name": "lamp", "type": "light"},
        headers=_bearer(3, "guest"),
    )
    assert response.status_code == 403


def test_technoking_only_route_rejects_resident_token(api_client):
    """PUT /api/system/config is technoking-only -- a resident token must 403, proving the
    per-resource role split (not just "any authenticated user passes")."""
    response = api_client.put(
        "/api/system/config", json={"key": "x"}, headers=_bearer(2, "resident")
    )
    assert response.status_code == 403


@patch("routes.devices.db_connection")
def test_write_route_succeeds_for_permitted_resident_token(mock_db_connection, api_client):
    """A resident token on a resident-allowed resource makes it all the way through
    require_permission into the actual route body."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.side_effect = [(1,), (1,), (1,)]  # state, type, environment lookups
    mock_cursor.lastrowid = 42

    response = api_client.post(
        "/api/devices",
        json={"name": "lamp", "type": "light"},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 201
    assert response.json()["id"] == 42


# --- DELETE /api/iot/devices/{id}: explicit removal of a synced smarthome device --


def test_delete_iot_device_rejects_unauthenticated_request(api_client):
    assert api_client.delete("/api/iot/devices/60").status_code == 401


def test_delete_iot_device_rejects_resident_token(api_client):
    """Removing a synced device is technoking-only (iot resource "*" grant) -- a resident
    can control devices but not delete their registry rows."""
    response = api_client.delete("/api/iot/devices/60", headers=_bearer(2, "resident"))
    assert response.status_code == 403


@patch("routes.iot.db_connection")
def test_delete_iot_device_404_when_missing(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    response = api_client.delete("/api/iot/devices/999", headers=_bearer(1, "owner"))
    assert response.status_code == 404


@patch("routes.iot.db_connection")
def test_delete_iot_device_clears_command_history_then_the_row(mock_db_connection, api_client):
    """device_command_history FKs smarthome_devices with no ON DELETE CASCADE, so its rows
    must be cleared before the device row or the DELETE errors."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (60, "Moonrise TV", "homeassistant")
    mock_cursor.fetchall.return_value = []

    response = api_client.delete("/api/iot/devices/60", headers=_bearer(1, "owner"))
    assert response.status_code == 200
    assert response.json()["device_id"] == 60

    deletes = [c.args[0] for c in mock_cursor.execute.call_args_list if "DELETE" in c.args[0]]
    assert deletes[0].startswith("DELETE FROM device_command_history")
    assert deletes[1].startswith("DELETE FROM smarthome_devices")


# --- PUT /api/users/{id}: self-service profile editing (todo_user_management.md) --


def test_put_user_rejects_unauthenticated_request(api_client):
    response = api_client.put("/api/users/2", json={"name": "New Name"})
    assert response.status_code == 401


def test_put_user_rejects_editing_someone_elses_row(api_client):
    """A resident (no `users` write grant) editing a different user's id must 403 -- there is
    no admin grant and it isn't their own row."""
    response = api_client.put(
        "/api/users/99", json={"name": "New Name"}, headers=_bearer(2, "resident")
    )
    assert response.status_code == 403


@patch("routes.users.db_connection")
def test_put_user_self_service_edit_succeeds(mock_db_connection, api_client):
    """A resident editing their own row (id matches the token's sub) goes through even though
    they have no `users` write grant -- this is the self-service bypass."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.put(
        "/api/users/2", json={"name": "New Name"}, headers=_bearer(2, "resident")
    )
    assert response.status_code == 200
    mock_cursor.execute.assert_called_once_with(
        "UPDATE user SET username = %s WHERE id = %s", ["New Name", 2]
    )


@patch("routes.users.db_connection")
def test_put_user_self_service_edit_sets_title(mock_db_connection, api_client):
    """A resident setting their own `title` (free-text form of address) is a plain field
    update, same self-service bypass as `name`."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.put(
        "/api/users/2", json={"title": "boss"}, headers=_bearer(2, "resident")
    )
    assert response.status_code == 200
    mock_cursor.execute.assert_called_once_with(
        "UPDATE user SET title = %s WHERE id = %s", ["boss", 2]
    )


@patch("routes.users.db_connection")
def test_put_user_self_service_edit_ignores_type_field(mock_db_connection, api_client):
    """A user including `type` in a self-edit payload must have it silently dropped, not
    applied -- self-service can never change your own role, even to a lesser one, so there's no
    privilege-escalation path through this route. No `user_types` lookup should even run."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.put(
        "/api/users/2",
        json={"name": "New Name", "type": "owner"},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 200
    mock_cursor.execute.assert_called_once_with(
        "UPDATE user SET username = %s WHERE id = %s", ["New Name", 2]
    )


@patch("routes.users.db_connection")
def test_put_user_admin_editing_own_row_also_drops_type(mock_db_connection, api_client):
    """Even an owner/technoking editing their *own* row via this route can't change their own
    `type` -- that must go through the explicit admin-on-someone-else path instead."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.put(
        "/api/users/1",
        json={"name": "New Name", "type": "resident"},
        headers=_bearer(1, "owner"),
    )
    assert response.status_code == 200
    mock_cursor.execute.assert_called_once_with(
        "UPDATE user SET username = %s WHERE id = %s", ["New Name", 1]
    )


@patch("routes.users.db_connection")
def test_put_user_admin_editing_someone_else_can_change_type(mock_db_connection, api_client):
    """Owner/technoking editing a *different* user's row is the one path that can still change
    `type` -- this is the real admin CRUD surface, unaffected by the self-service restriction."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (3,)  # user_types lookup for "guest"

    response = api_client.put(
        "/api/users/2",
        json={"type": "guest"},
        headers=_bearer(1, "owner"),
    )
    assert response.status_code == 200
    mock_cursor.execute.assert_any_call("SELECT id FROM user_types WHERE type = %s", ("guest",))
    mock_cursor.execute.assert_any_call("UPDATE user SET type = %s WHERE id = %s", [3, 2])


# --- POST /api/context/surface-state (todo_cross_surface_continuity.md) --


def test_surface_state_rejects_unauthenticated_request(api_client):
    response = api_client.post("/api/context/surface-state", json={"active_surface": "music"})
    assert response.status_code == 401


def test_surface_state_rejects_guest_role_token(api_client):
    response = api_client.post(
        "/api/context/surface-state",
        json={"active_surface": "music"},
        headers=_bearer(3, "guest"),
    )
    assert response.status_code == 403


@patch("routes.context.db_connection")
def test_surface_state_upserts_for_permitted_resident_token(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.rowcount = 1  # UPDATE "succeeds" -> no INSERT fallback

    response = api_client.post(
        "/api/context/surface-state",
        json={"active_surface": "music", "terminal_session_active": False},
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    update_calls = [c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1][1] == "launcher_surface_state"
    mock_db.commit.assert_called_once()


# --- POST /api/context/attention-telemetry (todo_attention_telemetry.md) --


def test_attention_telemetry_rejects_unauthenticated_request(api_client):
    response = api_client.post("/api/context/attention-telemetry", json={"unlock_count": 3})
    assert response.status_code == 401


def test_attention_telemetry_rejects_guest_role_token(api_client):
    response = api_client.post(
        "/api/context/attention-telemetry",
        json={"unlock_count": 3},
        headers=_bearer(3, "guest"),
    )
    assert response.status_code == 403


@patch("routes.context.db_connection")
def test_attention_telemetry_upserts_for_permitted_resident_token(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.rowcount = 0  # UPDATE affects nothing -> INSERT fallback

    response = api_client.post(
        "/api/context/attention-telemetry",
        json={
            "unlock_count": 5,
            "switch_count": 12,
            "dwell_by_category_ms": {"media": 600000, "terminal": 120000},
            "window_start_ms": 1000,
            "window_end_ms": 2000,
        },
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    insert_calls = [
        c for c in mock_cursor.execute.call_args_list if "INSERT INTO config" in c.args[0]
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[1][0] == "launcher_attention_telemetry"

    history_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if "INSERT INTO attention_telemetry_history" in c.args[0]
    ]
    assert len(history_calls) == 1
    assert history_calls[0].args[1][0] == 5  # unlock_count
    assert history_calls[0].args[1][1] == 12  # switch_count


# --- POST /api/context/device-location (todo_device_location_reporting.md) --

_INSTALL_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"


def _fix(lat=43.6532, lon=-79.3832, accuracy_m=850.0, provider="network", captured_at_ms=None):
    import time

    return {
        "latitude": lat,
        "longitude": lon,
        "accuracy_m": accuracy_m,
        "provider": provider,
        "captured_at_ms": captured_at_ms if captured_at_ms is not None else time.time() * 1000,
    }


def test_device_location_rejects_unauthenticated_request(api_client):
    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix()]},
    )
    assert response.status_code == 401


def test_device_location_rejects_guest_role_token(api_client):
    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix()]},
        headers=_bearer(3, "guest"),
    )
    assert response.status_code == 403


@patch("routes.context.db_connection")
def test_device_location_rejects_non_uuid_install_id(mock_db_connection, api_client):
    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": "not-a-uuid", "fixes": [_fix()]},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 400
    mock_db_connection.assert_not_called()


@patch("routes.context.db_connection")
def test_device_location_rejects_empty_fix_list(mock_db_connection, api_client):
    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": []},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 400
    mock_db_connection.assert_not_called()


@patch("routes.context.db_connection")
def test_device_location_inserts_batch_with_user_from_jwt(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(), _fix(lat=43.70, lon=-79.40)]},
        headers=_bearer(7, "resident"),
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 2, "rejected": 0}
    mock_cursor.executemany.assert_called_once()
    sql, rows = mock_cursor.executemany.call_args.args
    assert "INSERT INTO device_location_history" in sql
    assert len(rows) == 2
    # (client_install_id, user_id, lat, lon, accuracy, provider, source, captured_at, reported_at)
    assert rows[0][0] == _INSTALL_ID
    assert rows[0][1] == 7  # user_id from the token's sub, not the body
    assert rows[0][6] == "deck"
    mock_db.commit.assert_called_once()


@patch("routes.context.db_connection")
def test_device_location_drops_out_of_range_and_future_fixes(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    import time

    good = _fix()
    bad_lat = _fix(lat=120.0)
    future = _fix(captured_at_ms=(time.time() + 3600) * 1000)
    ancient = _fix(captured_at_ms=(time.time() - 400 * 86400) * 1000)

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [good, bad_lat, future, ancient]},
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": 3}
    rows = mock_cursor.executemany.call_args.args[1]
    assert len(rows) == 1


@patch("routes.context.db_connection")
def test_device_location_all_fixes_bad_makes_no_db_call(mock_db_connection, api_client):
    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(lat=999.0)]},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "rejected": 1}
    mock_db_connection.assert_not_called()


@patch("routes.context.db_connection")
def test_device_location_nulls_absurd_accuracy_but_keeps_the_fix(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(accuracy_m=999999.0)]},
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": 0}
    rows = mock_cursor.executemany.call_args.args[1]
    assert rows[0][4] is None  # accuracy_m nulled, fix still stored


# --- SA-12 geofence -> household_events producer (todo_transition_learning.md) ------------


class TestHaversineM:
    """Tests for routes.context._haversine_m()."""

    def test_same_point_is_zero(self, api_app):
        from routes.context import _haversine_m

        assert _haversine_m(43.6532, -79.3832, 43.6532, -79.3832) == 0.0

    def test_one_degree_latitude_is_roughly_111km(self, api_app):
        """Sanity-checks the formula against a well-known constant rather than a fixed-up
        expected value -- 1 degree of latitude is ~111.2km everywhere on Earth."""
        from routes.context import _haversine_m

        distance = _haversine_m(43.0, -79.0, 44.0, -79.0)
        assert 110_500 < distance < 111_500


class TestGeofenceState:
    """Tests for routes.context._geofence_state()."""

    def test_confidently_home_when_worst_case_still_inside_radius(self, api_app):
        from routes.context import _geofence_state

        assert _geofence_state(distance_m=50.0, accuracy_m=20.0, radius_m=300.0) == "home"

    def test_confidently_away_when_best_case_still_outside_radius(self, api_app):
        from routes.context import _geofence_state

        assert _geofence_state(distance_m=1000.0, accuracy_m=50.0, radius_m=300.0) == "away"

    def test_ambiguous_when_accuracy_straddles_the_radius(self, api_app):
        from routes.context import _geofence_state

        assert _geofence_state(distance_m=310.0, accuracy_m=100.0, radius_m=300.0) is None

    def test_no_accuracy_falls_back_to_a_plain_threshold(self, api_app):
        from routes.context import _geofence_state

        assert _geofence_state(distance_m=100.0, accuracy_m=None, radius_m=300.0) == "home"
        assert _geofence_state(distance_m=500.0, accuracy_m=None, radius_m=300.0) == "away"


class TestComputeGeofenceTransitions:
    """Tests for routes.context._compute_geofence_transitions()."""

    _HOME = (43.6532, -79.3832)
    _AWAY = (43.70, -79.40)  # ~5.5km from _HOME -- confidently "away" at any sane accuracy

    def test_no_baseline_establishes_state_without_emitting(self, api_app):
        """A brand-new install's very first fix has nothing to transition *from*."""
        from routes.context import _compute_geofence_transitions

        fixes = [(*self._AWAY, 50.0, "t1")]
        assert _compute_geofence_transitions(self._HOME, None, fixes) == []

    def test_home_to_away_emits_left_area(self, api_app):
        from routes.context import _compute_geofence_transitions

        fixes = [(*self._AWAY, 50.0, "t1")]
        assert _compute_geofence_transitions(self._HOME, "home", fixes) == [("left_area", "t1")]

    def test_away_to_home_emits_entered_area(self, api_app):
        from routes.context import _compute_geofence_transitions

        fixes = [(*self._HOME, 20.0, "t1")]
        assert _compute_geofence_transitions(self._HOME, "away", fixes) == [("entered_area", "t1")]

    def test_ambiguous_fix_does_not_flap_the_state(self, api_app):
        """A fix right on the boundary with poor accuracy is skipped entirely -- the next
        confidently-classified fix still compares against the last confident state, not the
        ambiguous one."""
        from routes.context import _compute_geofence_transitions

        fixes = [
            (43.6532, -79.3832 + 0.0027, 200.0, "ambiguous"),  # ~310m out, ±200m -- ambiguous
            (*self._AWAY, 50.0, "t2"),  # confidently away
        ]
        assert _compute_geofence_transitions(self._HOME, "home", fixes) == [("left_area", "t2")]

    def test_a_batch_spanning_a_round_trip_yields_both_crossings_in_order(self, api_app):
        """Fixes queued while offline and flushed together in one batch (e.g. a real short
        trip) must not collapse into "nothing changed" just because the last fix matches the
        starting state."""
        from routes.context import _compute_geofence_transitions

        fixes = [
            (*self._AWAY, 50.0, "left"),
            (*self._HOME, 20.0, "returned"),
        ]
        assert _compute_geofence_transitions(self._HOME, "home", fixes) == [
            ("left_area", "left"),
            ("entered_area", "returned"),
        ]


_HOME_ROW = (43.6532, -79.3832)


def _configure_geofence_mocks(mock_db_connection, home_row=_HOME_ROW, baseline_row=None):
    """Wires a mock cursor whose first fetchone() (home coordinates) returns `home_row` and
    whose second fetchone() (baseline fix) returns `baseline_row` -- the two SELECTs
    _emit_geofence_transition_events() issues, in that order."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.side_effect = [home_row, baseline_row]
    return mock_db, mock_cursor


@patch("routes.context.get_producer")
@patch("routes.context.db_connection")
def test_device_location_emits_left_area_event_on_home_to_away_crossing(
    mock_db_connection, mock_get_producer, api_client
):
    _configure_geofence_mocks(mock_db_connection, baseline_row=(_HOME_ROW[0], _HOME_ROW[1], 10.0))
    mock_producer = MagicMock()
    mock_get_producer.return_value = mock_producer

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(lat=43.70, lon=-79.40)]},
        headers=_bearer(9, "resident"),
    )

    assert response.status_code == 200
    mock_producer.send.assert_called_once()
    topic, event = mock_producer.send.call_args.args
    assert topic == "event-stream"
    assert event["subject_type"] == "user"
    assert event["subject_id"] == "9"
    assert event["verb"] == "left_area"
    assert event["service"] == "api"
    mock_producer.flush.assert_called_once()


@patch("routes.context.get_producer")
@patch("routes.context.db_connection")
def test_device_location_emits_no_event_without_home_coordinates_set(
    mock_db_connection, mock_get_producer, api_client
):
    _configure_geofence_mocks(mock_db_connection, home_row=(None, None))
    mock_producer = MagicMock()
    mock_get_producer.return_value = mock_producer

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(lat=43.70, lon=-79.40)]},
        headers=_bearer(9, "resident"),
    )

    assert response.status_code == 200
    mock_producer.send.assert_not_called()


@patch("routes.context.get_producer")
@patch("routes.context.db_connection")
def test_device_location_emits_no_event_for_a_brand_new_install_with_no_baseline(
    mock_db_connection, mock_get_producer, api_client
):
    _configure_geofence_mocks(mock_db_connection, baseline_row=None)
    mock_producer = MagicMock()
    mock_get_producer.return_value = mock_producer

    response = api_client.post(
        "/api/context/device-location",
        json={"client_install_id": _INSTALL_ID, "fixes": [_fix(lat=43.70, lon=-79.40)]},
        headers=_bearer(9, "resident"),
    )

    assert response.status_code == 200
    mock_producer.send.assert_not_called()


def test_card_interaction_rejects_unauthenticated_request(api_client):
    response = api_client.post(
        "/api/context/card-interaction", json={"rule_id": "music", "action": "shown"}
    )
    assert response.status_code == 401


def test_card_interaction_rejects_guest_role_token(api_client):
    response = api_client.post(
        "/api/context/card-interaction",
        json={"rule_id": "music", "action": "shown"},
        headers=_bearer(3, "guest"),
    )
    assert response.status_code == 403


@patch("routes.context.db_connection")
def test_card_interaction_rejects_invalid_action(mock_db_connection, api_client):
    response = api_client.post(
        "/api/context/card-interaction",
        json={"rule_id": "music", "action": "loved-it"},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 400
    mock_db_connection.assert_not_called()


@patch("routes.context.db_connection")
def test_card_interaction_rejects_missing_rule_id(mock_db_connection, api_client):
    response = api_client.post(
        "/api/context/card-interaction",
        json={"action": "shown"},
        headers=_bearer(2, "resident"),
    )
    assert response.status_code == 400
    mock_db_connection.assert_not_called()


@patch("routes.context.db_connection")
def test_card_interaction_inserts_for_permitted_resident_token(mock_db_connection, api_client):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.post(
        "/api/context/card-interaction",
        json={
            "rule_id": "rhythm_break_anomaly",
            "subject_key": "Living Room Lamp",
            "action": "dismissed",
        },
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    insert_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if "INSERT INTO card_interactions" in c.args[0]
    ]
    assert len(insert_calls) == 1
    params = insert_calls[0].args[1]
    assert params[0] == "rhythm_break_anomaly"
    assert params[1] == "Living Room Lamp"
    assert params[2] == "dismissed"
    mock_db.commit.assert_called_once()


@patch("routes.context.db_connection")
def test_card_interaction_defaults_subject_key_to_empty_string(mock_db_connection, api_client):
    """Singleton-identity rules (most of them) have no subject_key at all --
    the consumer just omits it."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.post(
        "/api/context/card-interaction",
        json={"rule_id": "weather", "action": "shown"},
        headers=_bearer(2, "resident"),
    )

    assert response.status_code == 200
    insert_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if "INSERT INTO card_interactions" in c.args[0]
    ]
    assert insert_calls[0].args[1][1] == ""


class TestInferSourceService:
    """Tests for app._infer_source_service() (SA-11 Phase 1)."""

    def test_prefers_an_explicit_service_key(self, api_app):
        from app import _infer_source_service

        assert _infer_source_service({"service": "device", "id": "user_x"}) == "device"

    def test_falls_back_to_id_prefix(self, api_app):
        from app import _infer_source_service

        assert _infer_source_service({"id": "user_online_20260829"}) == "user"
        assert _infer_source_service({"id": "song_start_20260829"}) == "daemon"
        assert _infer_source_service({"id": "personality_20260829"}) == "speak"
        assert _infer_source_service({"id": "weather_info_20260829"}) == "environment"
        assert _infer_source_service({"id": "calendar_event_created_20260829"}) == "daemon"
        assert _infer_source_service({"id": "calendar_event_removed_20260829"}) == "daemon"

    def test_unknown_id_prefix_falls_back_to_unknown(self, api_app):
        from app import _infer_source_service

        assert _infer_source_service({"id": "mystery_20260829"}) == "unknown"

    def test_missing_id_falls_back_to_unknown(self, api_app):
        from app import _infer_source_service

        assert _infer_source_service({}) == "unknown"


class TestParseEventTime:
    """Tests for app._parse_event_time() (SA-11 Phase 1)."""

    def test_parses_a_clean_isoformat_string(self, api_app):
        from app import _parse_event_time

        dt = _parse_event_time("2026-08-29T12:00:00+00:00")
        assert dt.year == 2026 and dt.hour == 12

    def test_tolerates_the_double_timezone_suffix_some_producers_emit(self, api_app):
        """service_user/service_environment/service_speak's send_event()
        appends a literal "Z" to an already-offset-bearing isoformat string
        (e.g. "...+00:00Z"), which datetime.fromisoformat rejects outright."""
        from app import _parse_event_time

        dt = _parse_event_time("2026-08-29T12:00:00+00:00Z")
        assert dt.year == 2026 and dt.hour == 12

    def test_missing_time_falls_back_to_now_rather_than_dropping(self, api_app):
        from app import _parse_event_time

        dt = _parse_event_time(None)
        assert dt.tzinfo is not None

    def test_unparseable_time_falls_back_to_now_rather_than_dropping(self, api_app):
        from app import _parse_event_time

        dt = _parse_event_time("not-a-timestamp")
        assert dt.tzinfo is not None


@patch("app.db_connection")
def test_persist_household_events_inserts_one_row_per_event(mock_db_connection, api_app):
    """Every event-stream message must produce exactly one durable row --
    the write-through side of SA-11 Phase 1."""
    import asyncio
    from app import _persist_household_events

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db_connection.return_value.__enter__.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    events = [
        {
            "id": "device_created_x",
            "type": "success",
            "message": "New device",
            "time": None,
            "subject_type": "device",
            "subject_id": "7",
            "verb": "created",
        },
        {"id": "personality_x", "type": "personality_state", "time": None},
    ]
    asyncio.run(_persist_household_events(events))

    insert_calls = [
        c
        for c in mock_cursor.executemany.call_args_list
        if "INSERT INTO household_events" in c.args[0]
    ]
    assert len(insert_calls) == 1
    rows = insert_calls[0].args[1]
    assert len(rows) == 2
    assert rows[0][0] == "success"
    assert rows[0][2:5] == ("device", "7", "created")
    assert rows[0][6] == "device"  # source_service
    assert rows[1][0] == "personality_state"
    assert rows[1][1] is None  # personality_state events carry no `message`
    assert rows[1][2:5] == (None, None, None)  # no structured fields yet
    assert rows[1][6] == "speak"  # source_service
    mock_db.commit.assert_called_once()


@patch("app.db_connection")
def test_persist_household_events_swallows_db_errors(mock_db_connection, api_app):
    """A DB hiccup while persisting must never propagate -- the in-memory
    recent_events buffer and its broadcast are the live dashboard feed and
    must keep working even if the durable write fails."""
    import asyncio
    from app import _persist_household_events

    mock_db_connection.side_effect = RuntimeError("db down")

    asyncio.run(_persist_household_events([{"id": "device_created_x", "type": "success"}]))


def test_persist_household_events_noop_on_empty_list(api_app):
    import asyncio
    from app import _persist_household_events

    asyncio.run(_persist_household_events([]))
