"""Tests for the ALFR3D daemon service utilities."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestCalendarUtils:
    """Tests for calendar_utils.py"""

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
        },
    )
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_success(self, mock_connect):
        """Test get_upcoming_events returns events when found."""
        from services.service_daemon.utils.calendar_utils import get_upcoming_events

        # Mock DB connection and cursor
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock fetchone to return an event
        mock_cursor.fetchone.return_value = (
            "Test Event",
            datetime.now() + timedelta(hours=1),
            "123 Main St",
            "Test notes",
        )

        result = get_upcoming_events()

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Test Event"
        assert result[0]["address"] == "123 Main St"
        assert result[0]["notes"] == "Test notes"
        mock_db.close.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
        },
    )
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_no_events(self, mock_connect):
        """Test get_upcoming_events returns None when no events found."""
        from services.service_daemon.utils.calendar_utils import get_upcoming_events

        # Mock DB connection and cursor
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock fetchone to return None
        mock_cursor.fetchone.return_value = None

        result = get_upcoming_events()

        assert result is None
        mock_db.close.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
        },
    )
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_db_error(self, mock_connect):
        """Test get_upcoming_events handles DB errors gracefully."""
        from services.service_daemon.utils.calendar_utils import get_upcoming_events

        # Mock connect to raise exception
        mock_connect.side_effect = Exception("DB connection failed")

        result = get_upcoming_events()

        assert result is None


class TestGmailUtils:
    """Tests for gmail_utils.py"""

    def test_check_unread_emails(self):
        """Test check_unread_emails returns None (placeholder)."""
        from services.service_daemon.utils.gmail_utils import check_unread_emails

        result = check_unread_emails()

        assert result is None


class TestMapsUtils:
    """Tests for maps_utils.py"""

    @patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test_key", "GAS_PRICE": "3.5", "MPG": "25"})
    def test_get_travel_info(self):
        """Test get_travel_info returns placeholder data."""
        from services.service_daemon.utils.maps_utils import get_travel_info

        event_time = datetime.now() + timedelta(hours=2)
        result = get_travel_info(40.7128, -74.0060, "123 Main St", event_time)

        assert result is not None
        assert "departure" in result
        assert "fuel_cost" in result
        assert result["fuel_cost"] == 5.0
        assert isinstance(result["departure"], datetime)


class TestSpotifyUtils:
    """Tests for spotify_utils.py"""

    def test_get_playlist_suggestion(self):
        """Test get_playlist_suggestion returns the hint."""
        from services.service_daemon.utils.spotify_utils import get_playlist_suggestion

        hint = "chill vibes"
        result = get_playlist_suggestion(hint)

        assert result == hint

    def test_recommend_single_person_morning(self):
        """Test recommend for single person in morning."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(1, 0, "morning")

        assert result["energy"] == 0.15  # 0.2 - 0.05
        assert result["mood"] == "relaxed acoustic"
        assert "acoustic" in result["genre"]

    def test_recommend_family_evening(self):
        """Test recommend for family in evening."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(4, 0, "evening")

        assert result["energy"] == 0.75  # 0.7 + 0.05
        assert result["mood"] == "upbeat alt-rock"
        assert "alt-rock" in result["genre"]

    def test_recommend_party_night_with_guests(self):
        """Test recommend for party with guests at night."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(8, 3, "night")

        assert result["energy"] == 1.0  # 0.9 + 0.08 + 0.05 = 1.03, clamped to 1.0
        assert result["mood"] == "energetic dance"
        assert "dance" in result["genre"]

    def test_recommend_with_weather_rain(self):
        """Test recommend adjusts for rainy weather."""
        from services.service_daemon.utils.spotify_utils import recommend

        weather = {"subjective_feel": "rainy", "description": "light rain", "temp": 15}
        result = recommend(3, 0, "day", weather)

        assert result["energy"] == 0.28  # 0.4 - 0.12
        assert "chill" in result["playlist_hint"]

    def test_recommend_with_weather_sunny(self):
        """Test recommend adjusts for sunny weather."""
        from services.service_daemon.utils.spotify_utils import recommend

        weather = {"subjective_feel": "sunny", "description": "clear sky", "temp": 25}
        result = recommend(3, 0, "day", weather)

        assert result["energy"] == 0.46  # 0.4 + 0.06
        assert "mellow" in result["playlist_hint"]

    def test_recommend_time_as_int(self):
        """Test recommend handles time_of_day as int."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(2, 0, 14)  # 2 PM = day

        assert result["mood"] == "warm indie"

    def test_recommend_none_time(self):
        """Test recommend defaults to 'day' when time_of_day is None."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(2, 0, None)

        assert result["mood"] == "warm indie"


class TestUtilRoutines:
    """Tests for util_routines.py"""

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        },
    )
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_check_routines_success(self, mock_connect):
        """Test checkRoutines processes enabled routines."""
        from services.service_daemon.utils.util_routines import check_routines

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock environment query
        mock_cursor.fetchone.side_effect = [
            (1,),  # environment id
            ((1, "Test Routine", timedelta(hours=10), None, 0),),  # routine
        ]

        result = check_routines()

        assert result is True
        mock_db.close.assert_called_once()

    @patch("services.service_daemon.utils.util_routines.ENV_NAME", "")
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_check_routines_no_env(self, mock_connect):
        """Test checkRoutines fails without environment name."""
        from services.service_daemon.utils.util_routines import check_routines

        result = check_routines()

        assert result is False

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        },
    )
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_reset_routines_success(self, mock_connect):
        """Test reset_routines resets triggered flags."""
        from services.service_daemon.utils.util_routines import reset_routines

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock queries
        mock_cursor.fetchone.side_effect = [(1,)]  # environment id
        mock_cursor.fetchall.return_value = [(1, "Test Routine")]  # routines

        result = reset_routines()

        assert result is True

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        },
    )
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_check_mute_during_day_with_users(self, mock_connect):
        """Test check_mute returns False during day with users online."""
        from services.service_daemon.utils.util_routines import check_mute

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock queries - morning at 8 AM, bed at 10 PM, current time 2 PM
        morning_time = timedelta(hours=8)
        bed_time = timedelta(hours=22)
        mock_cursor.fetchone.side_effect = [
            (1,),  # environment id
            (1, "Morning", morning_time, None, None),  # morning routine
            (2, "Bedtime", bed_time, None, None),  # bed routine
            (1,),  # online state id
        ]
        mock_cursor.fetchall.side_effect = [
            [(1,), (2,), (3,)],  # user types
            [(1, "user1", 1)],  # online users
        ]

        with patch("services.service_daemon.utils.util_routines.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 1, 14, 0)  # 2 PM
            mock_datetime.now.replace = MagicMock(
                side_effect=lambda **kwargs: datetime(2023, 1, 1, **kwargs)
            )

            result = check_mute()

        assert result is False  # Should not be mute during day with users

    @patch.dict(
        os.environ,
        {
            "MYSQL_DATABASE": "test_host",
            "MYSQL_USER": "root",
            "MYSQL_PSWD": "testrootpassword",
            "MYSQL_NAME": "test_alfr3d_db",
            "ALFR3D_ENV_NAME": "test_env",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        },
    )
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_check_mute_at_night_no_users(self, mock_connect):
        """Test check_mute returns True at night with no users online."""
        from services.service_daemon.utils.util_routines import check_mute

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock queries - morning at 8 AM, bed at 10 PM, current time 2 AM
        morning_time = timedelta(hours=8)
        bed_time = timedelta(hours=22)
        mock_cursor.fetchone.side_effect = [
            (1,),  # environment id
            (1, "Morning", morning_time, None, None),  # morning routine
            (2, "Bedtime", bed_time, None, None),  # bed routine
            (1,),  # online state id
        ]
        mock_cursor.fetchall.side_effect = [[(1,), (2,), (3,)], []]  # user types  # no users

        with patch("services.service_daemon.utils.util_routines.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 1, 2, 0)  # 2 AM
            mock_datetime.now.replace = MagicMock(
                side_effect=lambda **kwargs: datetime(2023, 1, 1, **kwargs)
            )

            result = check_mute()

        assert result is True  # Should be mute at night with no users
