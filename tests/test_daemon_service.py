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

    @patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "", "GAS_PRICE": "3.5", "MPG": "25"})
    @patch("services.service_daemon.utils.maps_utils.GOOGLE_MAPS_API_KEY", "")
    @patch("services.service_daemon.utils.maps_utils.GAS_PRICE", 3.5)
    @patch("services.service_daemon.utils.maps_utils.MPG", 25)
    def test_get_travel_info_no_api_key(self):
        """Test get_travel_info returns placeholder data without an API key."""
        from services.service_daemon.utils.maps_utils import get_travel_info

        event_time = datetime.now() + timedelta(hours=2)
        result = get_travel_info(40.7128, -74.0060, "123 Main St", event_time)

        assert result is not None
        assert "departure" in result
        assert "fuel_cost" in result
        assert result["fuel_cost"] == 5.0
        assert isinstance(result["departure"], datetime)

    @patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test_key", "GAS_PRICE": "3.5", "MPG": "25"})
    @patch("services.service_daemon.utils.maps_utils.GOOGLE_MAPS_API_KEY", "test_key")
    @patch("services.service_daemon.utils.maps_utils.GAS_PRICE", 3.5)
    @patch("services.service_daemon.utils.maps_utils.MPG", 25)
    def test_get_travel_info_with_api_key(self):
        """Test get_travel_info returns the fuel cost estimate with an API key set."""
        from services.service_daemon.utils.maps_utils import get_travel_info

        event_time = datetime.now() + timedelta(hours=2)
        result = get_travel_info(40.7128, -74.0060, "123 Main St", event_time)

        assert result is not None
        assert result["fuel_cost"] == round((3.5 / 25) * 10, 2)
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

    def test_get_routine_quip_returns_matching_quip(self):
        """Test routine quips are only fetched from the matching quip type."""
        from services.service_daemon.utils.util_routines import _get_routine_quip

        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(42,), ("yet another sunset",)]

        result = _get_routine_quip(mock_cursor, "sunset")

        assert result == "yet another sunset"
        calls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert "MAX(id)" in calls[0] and "type = %s" in calls[1]

    def test_get_routine_quip_returns_none_when_no_quips(self):
        """Test routine quip returns None when the type has no entries."""
        from services.service_daemon.utils.util_routines import _get_routine_quip

        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(None,)]

        result = _get_routine_quip(mock_cursor, "sunset")

        assert result is None


class TestDaemonRunLoop:
    """Tests for the daemon's main run loop routine reset behavior."""

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
    @patch("services.service_daemon.alfr3ddaemon.schedule.run_pending")
    @patch("services.service_daemon.alfr3ddaemon.time.sleep", side_effect=[None, Exception("stop")])
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.reset_routines")
    def test_run_resets_routines_on_local_day_change(
        self, mock_reset, mock_get_local_time, mock_sleep, mock_run_pending
    ):
        """Test routines are re-armed only when the env-local date rolls over."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        day1 = datetime(2026, 8, 7, 14, 0)
        day2 = datetime(2026, 8, 8, 0, 10)
        mock_get_local_time.side_effect = [day1, day2]

        with patch.object(MyDaemon, "scan_devices"), patch.object(
            MyDaemon, "check_routines"
        ), patch.object(MyDaemon, "check_mute_status", return_value=True), patch.object(
            MyDaemon, "perform_waking_hours_tasks"
        ), patch.object(
            MyDaemon, "check_situational_awareness"
        ):
            daemon = MyDaemon()
            try:
                daemon.run()
            except Exception:
                pass

        mock_reset.assert_called_once()

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
    @patch("services.service_daemon.alfr3ddaemon.schedule.run_pending")
    @patch("services.service_daemon.alfr3ddaemon.time.sleep", side_effect=[None, Exception("stop")])
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.reset_routines")
    def test_run_does_not_reset_within_same_local_day(
        self, mock_reset, mock_get_local_time, mock_sleep, mock_run_pending
    ):
        """Test routines are not reset multiple times within the same local day."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime(2026, 8, 7, 14, 0)
        mock_get_local_time.side_effect = [now, now]

        with patch.object(MyDaemon, "scan_devices"), patch.object(
            MyDaemon, "check_routines"
        ), patch.object(MyDaemon, "check_mute_status", return_value=True), patch.object(
            MyDaemon, "perform_waking_hours_tasks"
        ), patch.object(
            MyDaemon, "check_situational_awareness"
        ):
            daemon = MyDaemon()
            try:
                daemon.run()
            except Exception:
                pass

        mock_reset.assert_not_called()

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
    @patch("common.db_utils.datetime")
    @patch("common.db_utils.get_db_connection")
    def test_check_mute_during_day_with_users(self, mock_connect, mock_datetime):
        """Test check_mute returns False during day with users online."""
        from services.service_daemon.utils.util_routines import check_mute

        # Mock current time to 2 PM UTC (offset 0)
        mock_datetime.utcnow.return_value = datetime(2023, 1, 1, 14, 0)

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock queries - morning at 8 AM, bed at 10 PM, UTC timezone
        mock_cursor.fetchone.side_effect = [
            (timedelta(hours=8), timedelta(hours=22)),  # morning/bed routine times
            (0,),  # environment timezone offset (UTC)
        ]
        mock_cursor.fetchall.return_value = [(1, "user1")]  # online users

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
    @patch("common.db_utils.datetime")
    @patch("common.db_utils.get_db_connection")
    def test_check_mute_at_night_no_users(self, mock_connect, mock_datetime):
        """Test check_mute returns True at night with no users online."""
        from services.service_daemon.utils.util_routines import check_mute

        # Mock current time to 2 AM UTC (offset 0)
        mock_datetime.utcnow.return_value = datetime(2023, 1, 1, 2, 0)

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock queries - morning at 8 AM, bed at 10 PM, UTC timezone
        mock_cursor.fetchone.side_effect = [
            (timedelta(hours=8), timedelta(hours=22)),  # morning/bed routine times
            (0,),  # environment timezone offset (UTC)
        ]
        mock_cursor.fetchall.return_value = []  # no users online

        result = check_mute()

        assert result is True  # Should be mute at night with no users
