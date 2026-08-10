"""Tests for the ALFR3D environment service."""

import sys
import os
from unittest.mock import patch, MagicMock

# Add the service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_environment"))


@patch("services.service_environment.environment.get_producer")
@patch("services.service_environment.environment.pymysql.connect")
@patch("urllib.request.urlopen")
def test_check_location(mock_urlopen, mock_connect, mock_producer):
    """Test checkLocation function with mocked DB and API calls."""
    import environment

    os.environ["ALFR3D_ENV_NAME"] = "test"
    import importlib

    importlib.reload(environment)
    from unittest.mock import MagicMock

    # Mock producer
    mock_prod = MagicMock()
    mock_producer.return_value = mock_prod

    # Mock DB connection
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    # Mock existing environment in DB and config
    env_tuple = (
        1,
        "test",
        None,
        None,
        "OldCity",
        "OldState",
        "OldCountry",
        "oldip",
        None,
        None,
        None,
        None,
        None,
        None,
    )
    config_tuple = (
        1,
        "ipstack",
        "fake_api_key",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
    )
    mock_cursor.fetchone.side_effect = [env_tuple, config_tuple]

    # Mock IP fetch
    mock_ip_response = MagicMock()
    mock_ip_response.read.return_value.decode.return_value = "192.168.1.1"
    # Mock API response
    mock_api_response = MagicMock()
    mock_api_response.read.return_value = (
        '{"country_name": "NewCountry", "city": "NewCity", "ip": "192.168.1.1", '
        '"latitude": 10.0, "longitude": 20.0}'
    ).encode("utf-8")
    mock_urlopen.side_effect = [mock_ip_response, mock_api_response]

    # Call the function
    environment.check_location()

    # Assert DB update was called with new data
    mock_cursor.execute.assert_any_call(
        "UPDATE environment SET country = %s, state = %s, city = %s, IP = %s, "
        "latitude = %s, longitude = %s WHERE name = %s",
        ("NewCountry", "NewCountry", "NewCity", "192.168.1.1", 10.0, 20.0, "test"),
    )
    mock_db.commit.assert_called()


@patch("services.service_environment.environment.weather_util.get_weather")
@patch("services.service_environment.environment.pymysql.connect")
def test_check_weather(mock_connect, mock_weather):
    import environment

    """Test checkWeather function with mocked DB."""
    # Mock DB
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    # Mock environment with lat/long
    mock_cursor.fetchone.return_value = (
        1,
        "test",
        10.0,
        20.0,
        "City",
        "State",
        "Country",
        "ip",
        None,
        None,
        None,
        None,
        None,
        None,
    )

    # Call the function
    environment.check_weather()

    # Assert weather_util.getWeather was called with lat/long
    mock_weather.assert_called_with(10.0, 20.0)


@patch("services.service_frontend.app.get_connection")
def test_environment_service_frontend_integration(mock_connection, frontend_client):
    """Test frontend users endpoint."""
    # Mock DB
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connection.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("user1", "resident")]

    response = frontend_client.get("/api/users")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@patch("services.service_environment.weather_util.ALFR3D_ENV_NAME", "test")
def test_update_routines_does_not_reset_triggered():
    """Test update_routines syncs sun times but leaves the triggered flag alone."""
    import weather_util

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    # environment row with id 1
    mock_cursor.fetchone.return_value = (1, "test")
    # both Sunrise and Sunset routines already exist
    mock_cursor.fetchall.return_value = [("Sunrise",), ("Sunset",)]

    weather_data = {
        "sys": {"sunrise": 1723050000, "sunset": 1723094400},
        "timezone": -14400,
    }

    result = weather_util.update_routines(mock_db, mock_cursor, weather_data)

    assert result is True
    update_calls = [c for c in mock_cursor.execute.call_args_list if "UPDATE routines" in c[0][0]]
    assert len(update_calls) == 1
    assert "triggered" not in update_calls[0][0][0]
    mock_db.commit.assert_called()
