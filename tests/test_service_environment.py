"""Tests for the ALFR3D environment service."""
import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Add the service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'service_environment'))

@patch('services.service_environment.environment.get_producer')
@patch('services.service_environment.environment.pymysql.connect')
@patch('urllib.request.urlopen')
def test_check_location(mock_urlopen, mock_connect, mock_producer):
    """Test checkLocation function with mocked DB and API calls."""
    import os
    os.environ['ALFR3D_ENV_NAME'] = 'test'
    import environment as env
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
    env_tuple = (1, 'test', None, None, 'OldCity', 'OldState', 'OldCountry', 'oldip', None, None, None, None, None, None)
    config_tuple = (1, 'ipstack', 'fake_api_key', None, None, None, None, None, None, None, None, None, None, None, None, 0)
    mock_cursor.fetchone.side_effect = [env_tuple, config_tuple]

    # Mock IP fetch
    mock_ip_response = MagicMock()
    mock_ip_response.read.return_value.decode.return_value = '192.168.1.1'
    # Mock API response
    mock_api_response = MagicMock()
    mock_api_response.read.return_value.decode.return_value = '{"country_name": "NewCountry", "city": "NewCity", "ip": "192.168.1.1", "latitude": 10.0, "longitude": 20.0}'
    mock_urlopen.side_effect = [mock_ip_response, mock_api_response]

    # Call the function
    env.check_location()

    # Assert DB update was called with new data
    mock_cursor.execute.assert_any_call("UPDATE environment SET country = %s, state = %s, city = %s, IP = %s, latitude = %s, longitude = %s WHERE name = %s", ('NewCountry', 'NewCountry', 'NewCity', '192.168.1.1', 10.0, 20.0, 'test'))
    mock_db.commit.assert_called()

@patch('services.service_environment.environment.weather_util.getWeather')
@patch('services.service_environment.environment.pymysql.connect')
def test_check_weather(mock_connect, mock_weather):
    """Test checkWeather function with mocked DB."""
    # Mock DB
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_db
    mock_db.cursor.return_value = mock_cursor

    # Mock environment with lat/long
    mock_cursor.fetchone.return_value = (1, 'test', 10.0, 20.0, 'City', 'State', 'Country', 'ip', None, None, None, None, None, None)

    # Call the function
    env.check_weather()

    # Assert weather_util.getWeather was called with lat/long
    mock_weather.assert_called_with(10.0, 20.0)


def test_environment_service_frontend_integration(frontend_client):
    """Test environment service integration with frontend dashboard."""
    # Test that frontend can retrieve environment data
    response = frontend_client.get('/dashboard/data')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'environment' in data
    assert 'status' in data['environment']

    # Test environment page loads
    response = frontend_client.get('/environment')
    assert response.status_code == 200
    assert b'Environment' in response.data

    # Test command sending to environment service
    response = frontend_client.post('/command', data={'command': 'check_location'})
    assert response.status_code == 200
    assert b'Command sent' in response.data