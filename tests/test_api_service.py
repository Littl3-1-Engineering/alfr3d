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
            (1, "user1", "email1", "about1", "online", "resident", None, None),
            (2, "user2", "email2", "about2", "offline", "guest", None, None),
        ],
    )

    response = api_client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "user1"


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
    mock_db.commit.assert_called_once()
