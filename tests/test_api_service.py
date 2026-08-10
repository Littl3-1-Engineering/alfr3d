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


def _mock_connection(mock_connection, fetchall_value):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connection.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = fetchall_value
    return mock_db


@patch("dependencies.get_connection")
def test_api_health_check(mock_connection, api_client):
    """Test API health check endpoint."""
    _mock_connection(mock_connection, [])

    response = api_client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@patch("dependencies.get_connection")
def test_api_get_users(mock_connection, api_client):
    """Test get users endpoint."""
    _mock_connection(
        mock_connection,
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


@patch("dependencies.get_connection")
def test_api_get_devices(mock_connection, api_client):
    """Test get devices endpoint."""
    _mock_connection(
        mock_connection,
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
            ),
        ],
    )

    response = api_client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "device1"


def test_api_get_events(api_client):
    """Test get events endpoint."""
    response = api_client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
