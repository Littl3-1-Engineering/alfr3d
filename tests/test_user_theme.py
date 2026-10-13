"""Tests for the per-user shared UI theme endpoints (todo_theme_sync_deck.md)."""

import os
import sys
from unittest.mock import patch

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
os.environ.setdefault("HOST_REPO_PATH", "/tmp/alfr3d-test-repo")
os.environ.setdefault("COMPOSE_PROJECT_NAME", "alfr3d")


from auth.dependencies import CurrentUser, require_auth  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from app import app

    app.dependency_overrides[require_auth] = lambda: CurrentUser(id=7, type="resident")
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


def test_theme_requires_authentication():
    from app import app

    anon = TestClient(app)
    assert anon.get("/api/users/me/theme").status_code == 401
    assert anon.put("/api/users/me/theme", json={"theme": "dark"}).status_code == 401


def test_unknown_theme_rejected(client):
    assert client.put("/api/users/me/theme", json={"theme": "neon"}).status_code == 422


@patch("routes.users.manager.broadcast")
@patch("routes.users.db_connection")
def test_set_theme_saves_and_broadcasts_with_user_id(conn, broadcast, client):
    cursor = conn.return_value.__enter__.return_value.cursor.return_value
    resp = client.put("/api/users/me/theme", json={"theme": "amber"})
    assert resp.status_code == 200
    assert resp.json() == {"theme": "amber"}
    cursor.execute.assert_called_once_with(
        "UPDATE user SET ui_theme = %s WHERE id = %s", ("amber", 7)
    )
    broadcast.assert_awaited_once_with("theme", {"user_id": 7, "theme": "amber"})


@patch("routes.users.db_connection")
def test_get_theme_returns_value_or_null(conn, client):
    cursor = conn.return_value.__enter__.return_value.cursor.return_value
    cursor.fetchone.return_value = ("light",)
    assert client.get("/api/users/me/theme").json() == {"theme": "light"}
    cursor.fetchone.return_value = (None,)
    assert client.get("/api/users/me/theme").json() == {"theme": None}
