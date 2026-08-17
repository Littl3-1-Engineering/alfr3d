"""Tests for the ALFR3D environment service."""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import orjson

# Add the service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_environment"))


@patch("common.get_producer")
@patch("services.service_environment.environment.pymysql.connect")
@patch("urllib.request.urlopen")
def test_check_location(mock_urlopen, mock_connect, mock_producer):
    """Test checkLocation function with mocked DB and API calls."""
    import environment

    os.environ["ALFR3D_ENV_NAME"] = "test"
    import importlib

    # environment.py does `from common import get_producer`, so the mock must be
    # applied to common.get_producer *before* this reload re-executes that import
    # (patching environment.get_producer directly would be wiped out by reload,
    # which re-binds it from the now-unpatched real common.get_producer).
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
        0,  # manual_location_override (0 = auto location updates enabled)
        "OldCity",
        None,
        None,
        "OldState",
        "OldCountry",
        "oldip",
        None,
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


@patch("weather_util.datetime")
@patch("weather_util.get_cache")
@patch("weather_util.pymysql.connect")
@patch("weather_util.urlopen")
def test_get_forecast_parses_nearest_window(
    mock_urlopen, mock_connect, mock_get_cache, mock_datetime
):
    """get_forecast() returns the window nearest hours_ahead, parsing pop/temp/conditions.

    The "current time" is pinned via a mocked datetime rather than a real
    datetime.utcnow() call, since wall-clock deltas between test setup and
    the call inside get_forecast() would otherwise make the window boundary
    a race.
    """
    import weather_util

    fixed_now = datetime(2026, 8, 16, 12, 0, 0)
    mock_datetime.utcnow.return_value = fixed_now
    mock_datetime.utcfromtimestamp.side_effect = datetime.utcfromtimestamp

    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_get_cache.return_value = mock_cache

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1, "openWeather", "fake_api_key")

    def to_epoch(dt):
        return int((dt - datetime(1970, 1, 1)).total_seconds())

    forecast_response = {
        "list": [
            {
                "dt": to_epoch(fixed_now + timedelta(hours=3)),
                "main": {"temp": 15.0},
                "weather": [{"description": "light rain"}],
                "pop": 0.65,
            },
            {
                "dt": to_epoch(fixed_now + timedelta(hours=6)),
                "main": {"temp": 12.0},
                "weather": [{"description": "moderate rain"}],
                "pop": 0.8,
            },
        ]
    }
    mock_response = MagicMock()
    mock_response.read.return_value = orjson.dumps(forecast_response)
    mock_urlopen.return_value = mock_response

    result = weather_util.get_forecast(10.0, 20.0, hours_ahead=6)

    assert result == {
        "rain_probability": 80.0,
        "temp": 12.0,
        "conditions": "moderate rain",
    }
    mock_cache.set.assert_called_once()


@patch("weather_util.get_cache")
@patch("weather_util.pymysql.connect")
@patch("weather_util.urlopen")
def test_get_forecast_returns_none_on_network_error(mock_urlopen, mock_connect, mock_get_cache):
    """get_forecast() logs and returns None on an OWM API failure, matching get_weather()."""
    import weather_util

    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_get_cache.return_value = mock_cache

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1, "openWeather", "fake_api_key")

    mock_urlopen.side_effect = OSError("network down")

    result = weather_util.get_forecast(10.0, 20.0)

    assert result is None
    mock_cache.set.assert_not_called()


@patch("weather_util.get_cache")
@patch("weather_util.pymysql.connect")
def test_get_forecast_returns_none_without_api_key(mock_connect, mock_get_cache):
    """get_forecast() returns None (no crash) when no openWeather API key is configured."""
    import weather_util

    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_get_cache.return_value = mock_cache

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    result = weather_util.get_forecast(10.0, 20.0)

    assert result is None


@patch("weather_util.get_cache")
@patch("weather_util.urlopen")
def test_get_forecast_returns_cached_value_without_api_call(mock_urlopen, mock_get_cache):
    """A cache hit short-circuits the OWM call entirely."""
    import weather_util

    cached = {"rain_probability": 10.0, "temp": 18.0, "conditions": "clear sky"}
    mock_cache = MagicMock()
    mock_cache.get.return_value = cached
    mock_get_cache.return_value = mock_cache

    result = weather_util.get_forecast(10.0, 20.0)

    assert result == cached
    mock_urlopen.assert_not_called()


def test_update_db_forecast_persists_snapshot():
    """update_db_forecast() writes the forecast fields and commits."""
    import weather_util

    mock_db = MagicMock()
    mock_cursor = MagicMock()

    forecast = {"rain_probability": 55.0, "temp": 14.0, "conditions": "light rain"}
    result = weather_util.update_db_forecast(mock_db, mock_cursor, forecast)

    assert result is True
    mock_db.commit.assert_called()
    update_calls = [
        c for c in mock_cursor.execute.call_args_list if "UPDATE environment" in c[0][0]
    ]
    assert len(update_calls) == 1
    args = update_calls[0][0][1]
    assert args[0] == 55.0
    assert args[1] == 14.0
    assert args[2] == "light rain"


@patch("services.service_environment.environment.weather_util.update_db_forecast")
@patch("services.service_environment.environment.weather_util.get_forecast")
@patch("services.service_environment.environment.pymysql.connect")
def test_check_forecast_persists_a_successful_fetch(
    mock_connect, mock_get_forecast, mock_update_db_forecast
):
    """check_forecast() reads the home location, fetches a forecast, and
    persists it -- the orchestration wired up for P4 had no test at all."""
    import environment

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    # data[2]/data[3] are lat/long, matching check_weather()'s row shape.
    mock_cursor.fetchone.return_value = (1, "test", 10.0, 20.0, "City")

    forecast = {"rain_probability": 40.0, "temp": 18.0, "conditions": "clear sky"}
    mock_get_forecast.return_value = forecast

    environment.check_forecast()

    mock_get_forecast.assert_called_once_with(10.0, 20.0)
    mock_update_db_forecast.assert_called_once_with(mock_db, mock_cursor, forecast)
    mock_db.close.assert_called_once()


@patch("services.service_environment.environment.weather_util.update_db_forecast")
@patch("services.service_environment.environment.weather_util.get_forecast")
@patch("services.service_environment.environment.pymysql.connect")
def test_check_forecast_skips_persist_when_fetch_fails(
    mock_connect, mock_get_forecast, mock_update_db_forecast
):
    """A None forecast (e.g. OWM API failure) must not be persisted, and
    must not crash the caller."""
    import environment

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1, "test", 10.0, 20.0, "City")

    mock_get_forecast.return_value = None

    environment.check_forecast()

    mock_update_db_forecast.assert_not_called()
    mock_db.close.assert_called_once()


@patch("services.service_environment.environment.weather_util.get_forecast")
@patch("services.service_environment.environment.pymysql.connect")
def test_check_forecast_skips_fetch_when_no_location_data(mock_connect, mock_get_forecast):
    """No lat/long on file for this environment -- must not call the forecast
    API at all, mirroring check_weather()'s "no location data" behavior."""
    import environment

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1, "test", None, None, "City")

    environment.check_forecast()

    mock_get_forecast.assert_not_called()
    mock_db.close.assert_called_once()
