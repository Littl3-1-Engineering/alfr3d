"""Tests for the ALFR3D API service."""

import os
import sys
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_api"))


@pytest.fixture(scope="session")
def api_app():
    """FastAPI app fixture for API tests."""
    from app import app

    return app


@pytest.fixture(scope="session")
def api_client(api_app):
    """FastAPI TestClient for API tests."""
    return TestClient(api_app)


@patch("app.pymysql.connect")
def test_api_health_check(mock_connect, api_client):
    """Test API health check endpoint."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    response = api_client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@patch("app.pymysql.connect")
def test_api_get_users(mock_connect, api_client):
    """Test get users endpoint."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        (1, "user1", "email1", "about1", "online", "resident", None, None),
        (2, "user2", "email2", "about2", "offline", "guest", None, None),
    ]

    response = api_client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "user1"


@patch("app.pymysql.connect")
def test_api_get_devices(mock_connect, api_client):
    """Test get devices endpoint."""
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
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
    ]

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
