"""Tests for the ALFR3D daemon service utilities."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone


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
        """check_unread_emails is a real Gmail API implementation; it returns
        None here only because no OAuth credentials are configured in the test
        environment, not because it's a stub."""
        from services.service_daemon.utils.gmail_utils import check_unread_emails

        result = check_unread_emails()

        assert result is None


class TestSpotifyUtils:
    """Tests for spotify_utils.py"""

    def test_resolve_playlist_none_when_not_authorized(self):
        """Test resolve_playlist returns None gracefully when Spotify isn't connected."""
        from unittest.mock import patch
        from services.service_daemon.utils.spotify_utils import resolve_playlist

        with patch(
            "common.spotify_utils.find_playlist_for_hint",
            return_value=(None, "Spotify not connected"),
        ):
            result = resolve_playlist("chill vibes")

        assert result is None

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
        """Test recommend for party with guests at night, on a declared party night."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(8, 3, "night", is_party_night=True)

        assert result["energy"] == 1.0  # 0.9 + 0.08 + 0.05 = 1.03, clamped to 1.0
        assert result["mood"] == "energetic dance"
        assert "dance" in result["genre"]

    def test_recommend_weeknight_caps_energy_despite_big_gathering(self):
        """Same headcount/guests/time as the party-night test above, but without
        is_party_night -- energy must be capped below the party tier, not just
        happen to land lower."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(8, 3, "night")

        assert result["energy"] == 0.79
        assert result["mood"] != "energetic dance"
        assert "dance" not in result["genre"]

    def test_recommend_weeknight_cap_does_not_affect_already_low_energy(self):
        """The weeknight cap (0.79) must not raise energy that was already lower."""
        from services.service_daemon.utils.spotify_utils import recommend

        result = recommend(1, 0, "morning")

        assert result["energy"] == 0.15

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


class TestIsPartyNight:
    """Tests for common.spotify_utils.is_party_night()."""

    def test_friday_evening_is_party_night(self):
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 14, 20, 0)) is True  # Friday 8pm

    def test_saturday_night_is_party_night(self):
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 15, 22, 30)) is True  # Saturday 10:30pm

    def test_sunday_night_is_not_party_night(self):
        """The exact regression this whole feature exists for: Sunday night
        must not read as a party night no matter how late it is."""
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 16, 22, 0)) is False  # Sunday 10pm

    def test_thursday_night_is_not_party_night(self):
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 13, 23, 0)) is False  # Thursday 11pm

    def test_friday_afternoon_is_not_party_night(self):
        """Only Friday evening/night counts -- a Friday afternoon gathering
        doesn't inherit party-night status just because it's a Friday."""
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 14, 14, 0)) is False  # Friday 2pm

    def test_saturday_early_morning_still_reads_as_friday_night(self):
        """00:00-04:59 is attributed to the previous calendar day, so a
        Saturday 2am gathering is still "Friday night"."""
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 15, 2, 0)) is True  # Saturday 2am

    def test_sunday_early_morning_still_reads_as_saturday_night(self):
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 16, 2, 0)) is True  # Sunday 2am

    def test_monday_early_morning_is_not_party_night(self):
        """The previous-day attribution must not let a Monday 2am gathering
        inherit Sunday's (non-party) status as "party" by accident."""
        from datetime import datetime

        from services.common.spotify_utils import is_party_night

        assert is_party_night(datetime(2026, 8, 17, 2, 0)) is False  # Monday 2am

    def test_defaults_to_now_when_omitted(self):
        from services.common.spotify_utils import is_party_night

        assert is_party_night() in (True, False)


class TestNowPlayingMonitor:
    """Tests for now_playing_monitor.py"""

    @staticmethod
    def _state(track_id="t1", playing=True, title="Song One", artists=None, **overrides):
        item = None
        if track_id:
            item = {
                "id": track_id,
                "name": title,
                "artists": artists if artists is not None else ["Artist A"],
                "album": "Album One",
                "album_art": "http://img/art.jpg",
                "duration_ms": 180000,
                "uri": f"spotify:track:{track_id}",
            }
        state = {"is_playing": playing, "item": item, "progress_ms": 5000}
        state.update(overrides)
        return state

    def test_new_track_emits_playing_song_event(self):
        """A brand-new playing track publishes a 'playing song' event."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, new_track_id, new_is_playing = evaluate(self._state(), None, False)

        assert new_track_id == "t1"
        assert new_is_playing is True
        assert event is not None
        assert event["type"] == "audio"
        assert event["message"] == "playing song: Song One by Artist A"
        assert event["is_playing"] is True
        assert event["track"]["id"] == "t1"
        assert event["track"]["album_art"] == "http://img/art.jpg"
        assert "time" in event

    def test_track_change_emits_new_event(self):
        """A different track while playing publishes a fresh event."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, new_track_id, _ = evaluate(self._state(track_id="t2", title="Song Two"), "t1", True)

        assert new_track_id == "t2"
        assert event is not None
        assert event["message"] == "playing song: Song Two by Artist A"

    def test_same_track_playing_emits_nothing(self):
        """Repeated samples of the same playing track do not spam events."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, new_track_id, new_is_playing = evaluate(self._state(), "t1", True)

        assert event is None
        assert new_track_id == "t1"
        assert new_is_playing is True

    def test_playback_stop_emits_stopped_event(self):
        """Transition playing -> stopped publishes a stop event with no track."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, new_track_id, new_is_playing = evaluate(
            self._state(track_id=None, playing=False), "t1", True
        )

        assert event is not None
        assert event["message"] == "playback stopped"
        assert event["is_playing"] is False
        assert event["track"] is None
        assert new_track_id is None
        assert new_is_playing is False

    def test_stopped_stays_silent(self):
        """No duplicate stop events while playback stays stopped."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, _, _ = evaluate(self._state(track_id=None, playing=False), None, False)

        assert event is None

    def test_not_authorized_is_silent(self):
        """An un-authorized/error state emits nothing and resets tracking."""
        from services.service_daemon.utils.now_playing_monitor import evaluate

        event, new_track_id, new_is_playing = evaluate(
            {"authorized": False, "error": "Not authorized"}, "t1", True
        )

        assert event is None
        assert new_track_id is None
        assert new_is_playing is False

    @patch("services.service_daemon.utils.now_playing_monitor.get_producer")
    def test_monitor_loop_publishes_event(self, mock_get_producer):
        """The monitor loop publishes a song-start event via the Kafka producer."""
        from services.service_daemon.utils.now_playing_monitor import (
            monitor_now_playing,
        )

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]

        with patch(
            "services.service_daemon.utils.now_playing_monitor.spotify_api.get_playback_state",
            return_value=self._state(),
        ):
            monitor_now_playing(stop_event=stop_event, poll_interval=0)

        mock_producer.send.assert_called_once()
        args, _ = mock_producer.send.call_args
        assert args[0] == "event-stream"


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
    @patch("services.service_daemon.utils.util_routines.ENV_NAME", "test_env")
    @patch("services.service_daemon.utils.util_routines.db_utils.get_env_local_time")
    @patch("services.service_daemon.utils.util_routines.MySQLdb.connect")
    def test_check_routines_success(self, mock_connect, mock_local_time):
        """Test checkRoutines processes enabled routines."""
        from services.service_daemon.utils.util_routines import check_routines

        # Mock DB
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_local_time.return_value = datetime(2026, 8, 7, 14, 0)

        # Mock environment query (22 explicit columns, same order as the SELECT)
        env_row = (
            1,  # id
            None,  # latitude
            None,  # longitude
            "Testville",  # city
            "Test",  # state
            "Testland",  # country
            "127.0.0.1",  # IP
            0,  # low
            30,  # high
            20,  # temperature
            5,  # wind
            "N",  # wind_dir
            "clear",  # description
            None,  # sunrise
            None,  # sunset
            1013,  # pressure
            "steady",  # pressure_trend
            50,  # humidity
            0,  # manual_override
            0,  # manual_location_override
            "clear",  # subjective_feel
            0,  # timezone
        )
        mock_cursor.fetchone.return_value = env_row
        mock_cursor.fetchall.side_effect = [
            [],  # user states
            [],  # device states
            [
                (
                    1,
                    "Test Routine",
                    timedelta(hours=10),
                    1,
                    "daily",
                    None,
                    0,
                    None,
                    None,
                )
            ],  # routines
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
    @patch(
        "services.service_daemon.alfr3ddaemon.time.sleep",
        side_effect=[None, Exception("stop")],
    )
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
    @patch(
        "services.service_daemon.alfr3ddaemon.time.sleep",
        side_effect=[None, Exception("stop")],
    )
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


class TestDecideDisplays:
    """Tests for MyDaemon.decide_displays() and its DISPLAY_RULES registry."""

    TIME_CARD = {"mode": "time", "content": "t", "priority": 1}
    EVENT_CARD = {"mode": "event", "content": "e", "priority": 2}
    MUSIC_CARD = {"mode": "music", "content": "m", "priority": 3}
    NOW_PLAYING_CARD = {"mode": "music", "content": "np", "priority": 3.1}
    PARTY_ADVISORY_CARD = {"mode": "party_advisory", "content": "pa", "priority": 3.2}
    FOCUS_CARD = {"mode": "focus_needed", "content": "f", "priority": 3.5}
    EMAIL_CARD = {"mode": "email", "content": "em", "priority": 4}
    WEATHER_ADVISORY_CARD = {
        "mode": "weather_advisory",
        "content": "wa",
        "priority": 4.5,
    }
    WEATHER_CARD = {"mode": "weather", "content": "w", "priority": 5}
    MOOD_CARD = {
        "mode": "mood",
        "content": "Tuesday evening — moderate energy",
        "priority": 6,
    }
    HOUSEHOLD_COMPOSITION_CARD = {
        "mode": "household_composition",
        "content": "Home: athos",
        "priority": 6.2,
        "known_count": 1,
        "unknown_count": 0,
        "urgent": False,
    }
    RHYTHM_BREAK_ANOMALY_CARD = {
        "mode": "rhythm_break_anomaly",
        "content": "Garage light has been on for 42 min longer than usual",
        "priority": 2.6,
        "entity_name": "Garage light",
        "deviation_type": "still_on_past_typical",
    }
    CROSS_SURFACE_CONTINUITY_CARD = {
        "mode": "cross_surface_continuity",
        "content": "Song paused 4 min ago — resume on the Deck?",
        "priority": 5.5,
        "resume_type": "music",
        "resume_target": "track1",
    }
    ATTENTION_FOCUS_CARD = {
        "mode": "attention_focus",
        "content": "Deep in it — 20 window switches recently",
        "priority": 3.6,
        "switch_count": 20,
    }
    WIND_DOWN_SIGNAL_CARD = {
        "mode": "wind_down_signal",
        "content": "Lots of screen time tonight (8 unlocks) — wind down?",
        "priority": 5.8,
        "unlock_count": 8,
    }

    def _stub_daemon(
        self,
        check_time=None,
        check_events=None,
        check_gatherings=None,
        check_now_playing=None,
        check_party_advisory=None,
        check_focus_needed=None,
        check_emails=None,
        check_weather_advisory=None,
        check_weather=None,
        check_mood=None,
        check_household_composition=None,
        check_rhythm_break_anomaly=None,
        check_cross_surface_continuity=None,
        check_attention_focus=None,
        check_wind_down_signal=None,
    ):
        """Build a MyDaemon with each check_* replaced by a stub returning the given card."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        daemon.check_time = MagicMock(return_value=check_time)
        daemon.check_events = MagicMock(return_value=check_events)
        daemon.check_gatherings = MagicMock(return_value=check_gatherings)
        daemon.check_now_playing = MagicMock(return_value=check_now_playing)
        daemon.check_party_advisory = MagicMock(return_value=check_party_advisory)
        daemon.check_focus_needed = MagicMock(return_value=check_focus_needed)
        daemon.check_emails = MagicMock(return_value=check_emails)
        daemon.check_weather_advisory = MagicMock(return_value=check_weather_advisory)
        daemon.check_weather = MagicMock(return_value=check_weather)
        daemon.check_mood = MagicMock(return_value=check_mood)
        daemon.check_household_composition = MagicMock(return_value=check_household_composition)
        daemon.check_rhythm_break_anomaly = MagicMock(return_value=check_rhythm_break_anomaly)
        daemon.check_attention_focus = MagicMock(return_value=check_attention_focus)
        daemon.check_wind_down_signal = MagicMock(return_value=check_wind_down_signal)
        daemon.check_cross_surface_continuity = MagicMock(
            return_value=check_cross_surface_continuity
        )
        return daemon

    def test_all_ten_checks_produce_cards_in_priority_order(self):
        """When every check fires, cards come back sorted by priority (time..household)."""
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=self.EVENT_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_now_playing=self.NOW_PLAYING_CARD,
            check_party_advisory=self.PARTY_ADVISORY_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
            check_weather_advisory=self.WEATHER_ADVISORY_CARD,
            check_weather=self.WEATHER_CARD,
            check_mood=self.MOOD_CARD,
            check_household_composition=self.HOUSEHOLD_COMPOSITION_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
            check_cross_surface_continuity=self.CROSS_SURFACE_CONTINUITY_CARD,
            check_attention_focus=self.ATTENTION_FOCUS_CARD,
            check_wind_down_signal=self.WIND_DOWN_SIGNAL_CARD,
        )

        result = daemon.decide_displays()

        assert [card["mode"] for card in result] == [
            "time",
            "event",
            "rhythm_break_anomaly",
            "music",
            "music",
            "party_advisory",
            "focus_needed",
            "attention_focus",
            "email",
            "weather_advisory",
            "weather",
            "cross_surface_continuity",
            "wind_down_signal",
            "mood",
            "household_composition",
        ]

    def test_weather_and_mood_are_not_dropped_when_everything_fires(self):
        """Regression test for the drop-at-4 bug: no registered rule loses its card to the cap."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=self.EVENT_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_now_playing=self.NOW_PLAYING_CARD,
            check_party_advisory=self.PARTY_ADVISORY_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
            check_weather_advisory=self.WEATHER_ADVISORY_CARD,
            check_weather=self.WEATHER_CARD,
            check_mood=self.MOOD_CARD,
            check_household_composition=self.HOUSEHOLD_COMPOSITION_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
            check_cross_surface_continuity=self.CROSS_SURFACE_CONTINUITY_CARD,
            check_attention_focus=self.ATTENTION_FOCUS_CARD,
            check_wind_down_signal=self.WIND_DOWN_SIGNAL_CARD,
        )

        result = daemon.decide_displays()

        assert len(result) == len(MyDaemon.DISPLAY_RULES)
        assert self.WEATHER_ADVISORY_CARD in result
        assert self.WEATHER_CARD in result
        assert self.MOOD_CARD in result
        assert self.FOCUS_CARD in result
        assert self.NOW_PLAYING_CARD in result
        assert self.PARTY_ADVISORY_CARD in result
        assert self.HOUSEHOLD_COMPOSITION_CARD in result
        assert self.RHYTHM_BREAK_ANOMALY_CARD in result
        assert self.CROSS_SURFACE_CONTINUITY_CARD in result
        assert self.ATTENTION_FOCUS_CARD in result
        assert self.WIND_DOWN_SIGNAL_CARD in result

    def test_focus_needed_sorts_between_music_and_email(self):
        """focus_needed (priority 3.5) lands between music (3) and email (4) when both fire."""
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
        )

        result = daemon.decide_displays()

        assert [card["mode"] for card in result] == [
            "time",
            "music",
            "focus_needed",
            "email",
        ]

    def test_none_results_are_excluded_without_crashing(self):
        """Checks that return None must not appear in the output or raise."""
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=None,
            check_gatherings=None,
            check_emails=None,
            check_weather=self.WEATHER_CARD,
        )

        result = daemon.decide_displays()

        assert None not in result
        assert [card["mode"] for card in result] == ["time", "weather"]

    def test_sorting_is_correct_for_an_arbitrary_subset(self):
        """A non-contiguous subset of firing checks still sorts correctly by priority."""
        daemon = self._stub_daemon(
            check_time=None,
            check_events=self.EVENT_CARD,
            check_gatherings=None,
            check_emails=self.EMAIL_CARD,
            check_weather=self.WEATHER_CARD,
        )

        result = daemon.decide_displays()

        assert [card["mode"] for card in result] == ["event", "email", "weather"]

    def test_no_registered_rule_shares_a_priority_with_another(self):
        """Regression guard: a future PR adding a category with an already-used
        priority should fail here, not surface as a silent sort-order bug."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        priorities = [priority for _rule_id, priority, _check_name in MyDaemon.DISPLAY_RULES]

        assert len(priorities) == len(set(priorities))

    def test_all_categories_firing_simultaneously_is_sorted_capped_and_collision_free(
        self,
    ):
        """End-to-end test of decide_displays() with the full, current category set
        (all fifteen DISPLAY_RULES entries) firing at once.

        This is the test to extend when a future PR registers a sixteenth category:
        add its card to the `self._stub_daemon(...)` call below and to the
        expected `modes` list in priority order.
        """
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=self.EVENT_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_now_playing=self.NOW_PLAYING_CARD,
            check_party_advisory=self.PARTY_ADVISORY_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
            check_weather_advisory=self.WEATHER_ADVISORY_CARD,
            check_weather=self.WEATHER_CARD,
            check_mood=self.MOOD_CARD,
            check_household_composition=self.HOUSEHOLD_COMPOSITION_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
            check_cross_surface_continuity=self.CROSS_SURFACE_CONTINUITY_CARD,
            check_attention_focus=self.ATTENTION_FOCUS_CARD,
            check_wind_down_signal=self.WIND_DOWN_SIGNAL_CARD,
        )

        result = daemon.decide_displays()

        # Sorted ascending by priority.
        priorities = [card["priority"] for card in result]
        assert priorities == sorted(priorities)

        # Cap behavior: MAX_DISPLAYS == len(DISPLAY_RULES), and every registered
        # rule fired exactly once, so all fifteen cards come back -- nothing dropped.
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert len(result) == 15 == MyDaemon.MAX_DISPLAYS == len(MyDaemon.DISPLAY_RULES)

        # No two cards silently collide on priority value.
        # (music and now_playing intentionally share mode "music" at different
        # priorities -- 3 vs 3.1 -- so they don't collide on priority either.)
        assert len(priorities) == len(set(priorities))

        assert [card["mode"] for card in result] == [
            "time",
            "event",
            "rhythm_break_anomaly",
            "music",
            "music",
            "party_advisory",
            "focus_needed",
            "attention_focus",
            "email",
            "weather_advisory",
            "weather",
            "cross_surface_continuity",
            "wind_down_signal",
            "mood",
            "household_composition",
        ]

    def test_partial_firing_set_still_sorts_and_caps_correctly(self):
        """Only a subset of categories fire (time, focus_needed, mood) -- a
        different code path from "all fire": the registry/sort/cap logic must
        not assume every category is always present."""
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_mood=self.MOOD_CARD,
        )

        result = daemon.decide_displays()

        assert [card["mode"] for card in result] == ["time", "focus_needed", "mood"]
        priorities = [card["priority"] for card in result]
        assert priorities == sorted(priorities)
        assert len(priorities) == len(set(priorities))
        assert len(result) == 3

    def test_no_checks_firing_returns_an_empty_list_without_crashing(self):
        """Every check returns None -- decide_displays() must not crash and
        must return an empty list (not None, not a default time/weather pair).

        Note: the "No priority displays, defaulting to time and weather" log
        message logged in this branch is stale/misleading -- no such
        defaulting is actually implemented. Flagged separately as a
        documentation/logging bug, not fixed here (out of scope for a
        coverage-only PR).
        """
        daemon = self._stub_daemon()

        result = daemon.decide_displays()

        assert result == []


class TestMoodUtils:
    """Tests for mood_utils.get_day_mood()."""

    def test_time_of_day_boundary_hours(self):
        """Each morning/day/evening/night boundary lands in the correct bucket."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        # Tuesday 2026-08-11: plain weekday, no weekend/Friday bonus applies.
        cases = [
            (datetime(2026, 8, 11, 5, 59), "night"),
            (datetime(2026, 8, 11, 6, 0), "morning"),
            (datetime(2026, 8, 11, 11, 59), "morning"),
            (datetime(2026, 8, 11, 12, 0), "day"),
            (datetime(2026, 8, 11, 17, 59), "day"),
            (datetime(2026, 8, 11, 18, 0), "evening"),
            (datetime(2026, 8, 11, 21, 59), "evening"),
            (datetime(2026, 8, 11, 22, 0), "night"),
        ]
        for when, expected in cases:
            result = get_day_mood(when)
            assert result["time_of_day"] == expected, f"{when} expected {expected}"

    def test_weekday_evening_has_no_bonus(self):
        """A plain Tuesday evening gets the unmodified evening baseline."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 11, 19, 0))  # Tuesday

        assert result["day_of_week"] == "Tuesday"
        assert result["is_weekend"] is False
        assert result["base_energy"] == 0.55

    def test_saturday_evening_gets_weekend_bonus(self):
        """A Saturday evening is bumped above the plain evening baseline."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 15, 19, 0))  # Saturday

        assert result["day_of_week"] == "Saturday"
        assert result["is_weekend"] is True
        assert result["base_energy"] == 0.70  # 0.55 evening baseline + 0.15 bonus

    def test_friday_evening_gets_wind_up_bonus_despite_not_being_weekend(self):
        """Friday evening/night gets the same bonus as the weekend, but is_weekend is False."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 14, 20, 0))  # Friday

        assert result["day_of_week"] == "Friday"
        assert result["is_weekend"] is False
        assert result["base_energy"] == 0.70  # 0.55 evening baseline + 0.15 bonus

    def test_friday_daytime_has_no_bonus(self):
        """Friday during the day (not evening/night) doesn't get the wind-up bonus."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 14, 14, 0))  # Friday afternoon

        assert result["base_energy"] == 0.50  # plain day baseline, no bonus

    def test_defaults_to_now_when_omitted(self):
        """Calling with no argument doesn't crash and returns a well-formed dict."""
        from services.service_daemon.utils.mood_utils import get_day_mood

        result = get_day_mood()

        assert result["time_of_day"] in ("morning", "day", "evening", "night")
        assert isinstance(result["is_weekend"], bool)
        assert 0.0 <= result["base_energy"] <= 1.0


class TestCheckMood:
    """Tests for MyDaemon.check_mood()."""

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
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_returns_well_formed_mood_card(self, mock_get_local_time):
        """check_mood() returns a well-formed card with a non-empty content string."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 19, 0)  # Tuesday evening

        daemon = MyDaemon()
        card = daemon.check_mood()

        assert card["mode"] == "mood"
        assert isinstance(card["content"], str) and card["content"]
        assert card["priority"] == 6
        # Priority must not collide with any other registered rule.
        other_priorities = {
            priority for rule_id, priority, _ in MyDaemon.DISPLAY_RULES if rule_id != "mood"
        }
        assert card["priority"] not in other_priorities

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
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_low_energy_label_at_night(self, mock_get_local_time):
        """Night baseline energy (0.30) must land in the 'low energy' bucket."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 2, 0)  # Tuesday 2am

        daemon = MyDaemon()
        card = daemon.check_mood()

        assert "low energy" in card["content"]

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
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_high_energy_label_on_saturday_evening(self, mock_get_local_time):
        """Weekend-bonus energy (0.70) must land in the 'high energy' bucket."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 15, 19, 0)  # Saturday evening

        daemon = MyDaemon()
        card = daemon.check_mood()

        assert "high energy" in card["content"]


class TestCheckGatherings:
    """Regression tests for check_gatherings()'s time_of_day wiring after mood_utils extraction."""

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
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.resolve_playlist")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.recommend")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_morning_gathering_passes_morning_time_of_day_to_recommend(
        self,
        mock_connect,
        mock_get_local_time,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """A gathering detected at 9am must be bucketed as 'morning', not 'day' or 'night'.

        Prior to the mood_utils extraction, check_gatherings() used its own 3-bucket
        inline logic (day/evening/night, no morning) which would have mis-bucketed
        this as "day". This is a regression test for that drift being fixed.
        """
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 9, 0)  # Tuesday 9am

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            (2, 5),  # guest_count, total_count
            ("Clear", "Nice"),  # description, subjective_feel
        ]
        mock_producer.return_value = None
        mock_resolve.return_value = None
        mock_recommend.return_value = {
            "mood": "warm indie",
            "genre": "indie",
            "energy": 0.5,
            "tempo_hint": "medium",
            "playlist_hint": "indie, mellow",
        }

        daemon = MyDaemon()
        daemon.check_gatherings()

        assert mock_recommend.call_args.kwargs["time_of_day"] == "morning"

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_and_rolls_back_on_db_error(self, mock_connect):
        """A pymysql.Error while querying gathering state must not crash
        decide_displays() -- the card is just skipped, same as the other
        DB-backed checks."""
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        daemon = MyDaemon()
        result = daemon.check_gatherings()

        assert result is None
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

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
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.resolve_playlist")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.recommend")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_resolved_playlist_fields_are_attached_to_the_card(
        self,
        mock_connect,
        mock_get_local_time,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """When spotify_utils.resolve_playlist() finds a real playlist, its
        fields (id/name/uri/url/image/source) must land on the returned card
        -- this is what the frontend's playlist-link rendering depends on."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 19, 0)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [(2, 5), ("Clear", "Nice")]
        mock_producer.return_value = None
        mock_recommend.return_value = {
            "mood": "warm indie",
            "genre": "indie",
            "energy": 0.5,
            "tempo_hint": "medium",
            "playlist_hint": "indie, mellow",
        }
        mock_resolve.return_value = {
            "id": "abc123",
            "name": "Indie Chill",
            "uri": "spotify:playlist:abc123",
            "url": "https://open.spotify.com/playlist/abc123",
            "image": "https://img.example.com/abc123.jpg",
            "source": "search",
        }

        daemon = MyDaemon()
        card = daemon.check_gatherings()

        assert card["playlist_id"] == "abc123"
        assert card["playlist_name"] == "Indie Chill"
        assert card["playlist_uri"] == "spotify:playlist:abc123"
        assert card["playlist_url"] == "https://open.spotify.com/playlist/abc123"
        assert card["playlist_image"] == "https://img.example.com/abc123.jpg"
        assert card["playlist_source"] == "search"
        assert "Indie Chill" in card["content"]

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
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.resolve_playlist")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.recommend")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_publishes_event_stream_message_when_producer_available(
        self,
        mock_connect,
        mock_get_local_time,
        mock_get_producer,
        mock_recommend,
        mock_resolve,
    ):
        """A gathering-detected event is published to the event-stream topic
        when a Kafka producer is available."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 19, 0)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [(2, 5), ("Clear", "Nice")]
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer
        mock_recommend.return_value = {
            "mood": "warm indie",
            "genre": "indie",
            "energy": 0.5,
            "tempo_hint": "medium",
            "playlist_hint": "indie, mellow",
        }
        mock_resolve.return_value = None

        daemon = MyDaemon()
        daemon.check_gatherings()

        event_stream_calls = [
            c for c in mock_producer.send.call_args_list if c.args[0] == "event-stream"
        ]
        assert len(event_stream_calls) == 1

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
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.resolve_playlist")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.recommend")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_playlist_resolution_exception_falls_back_to_text_hint(
        self,
        mock_connect,
        mock_get_local_time,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """resolve_playlist() raising must not crash check_gatherings() --
        it falls back to the plain text hint, with no playlist_* fields."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 19, 0)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [(2, 5), ("Clear", "Nice")]
        mock_producer.return_value = None
        mock_recommend.return_value = {
            "mood": "warm indie",
            "genre": "indie",
            "energy": 0.5,
            "tempo_hint": "medium",
            "playlist_hint": "indie, mellow",
        }
        mock_resolve.side_effect = Exception("Spotify API down")

        daemon = MyDaemon()
        card = daemon.check_gatherings()

        assert card is not None
        assert "playlist_id" not in card
        assert "indie, mellow" in card["content"]

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_guests_online(self, mock_connect):
        """No guests online (only residents, or nobody) -- no gathering card,
        and no Spotify recommendation call is made."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (0, 3)  # guest_count=0, total_count=3

        daemon = MyDaemon()
        result = daemon.check_gatherings()

        assert result is None


class TestCheckHouseholdComposition:
    """Tests for MyDaemon.check_household_composition()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_all_online_devices_claimed_is_ambient_priority(self, mock_connect):
        """Every online device belongs to a known household member -- low-urgency
        ambient card, same priority tier as mood."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("athos", "Athos's Phone"),
            ("athos", "Athos's Laptop"),
        ]

        daemon = MyDaemon()
        result = daemon.check_household_composition()

        assert result["mode"] == "household_composition"
        assert result["priority"] == 6.2
        assert result["urgent"] is False
        assert result["known_count"] == 1
        assert result["unknown_count"] == 0

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_unclaimed_device_online_is_elevated_priority(self, mock_connect):
        """An unclaimed/unknown MAC on the network -- elevated, security-relevant
        priority regardless of how many known members are also home."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("athos", "Athos's Phone"),
            (None, "Unclaimed Device"),
        ]

        daemon = MyDaemon()
        result = daemon.check_household_composition()

        assert result["priority"] == 2.3
        assert result["urgent"] is True
        assert result["known_count"] == 1
        assert result["unknown_count"] == 1

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_devices_online(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        daemon = MyDaemon()
        result = daemon.check_household_composition()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        daemon = MyDaemon()
        result = daemon.check_household_composition()

        assert result is None
        mock_db.close.assert_called_once()


class TestCheckRhythmBreakAnomaly:
    """Tests for MyDaemon.check_rhythm_break_anomaly()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_card_when_a_device_is_past_its_typical_max(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Garage light", 90, 60)

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly()

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["priority"] == 2.6
        assert result["entity_name"] == "Garage light"
        assert result["deviation_type"] == "still_on_past_typical"
        assert "30 min" in result["content"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_device_exceeds_its_baseline(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly()

        assert result is None
        mock_db.close.assert_called_once()


class TestComputeEntityBaselines:
    """Tests for compute_entity_baselines()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_upserts_a_baseline_from_reconstructed_sessions(self, mock_connect):
        """Three online->offline pairs for one device should produce one
        upsert with the median/typical-hour/min/max derived from those
        three sessions, and a commit."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        online_hour = datetime(2026, 8, 1, 9, 0)
        sessions = [
            (online_hour, "online"),
            (online_hour + timedelta(minutes=60), "offline"),
            (online_hour + timedelta(days=1), "online"),
            (online_hour + timedelta(days=1, minutes=90), "offline"),
            (online_hour + timedelta(days=2), "online"),
            (online_hour + timedelta(days=2, minutes=120), "offline"),
            (online_hour + timedelta(days=3), "online"),
            (online_hour + timedelta(days=3, minutes=60), "offline"),
            (online_hour + timedelta(days=4), "online"),
            (online_hour + timedelta(days=4, minutes=60), "offline"),
        ]
        mock_cursor.fetchall.side_effect = [[(42,)], sessions]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 1
        params = upsert_calls[0].args[1]
        assert params[0] == 42  # device_id
        assert params[1] == 60  # median_on_minutes (60, 90, 120, 60, 60 -> median 60)
        assert params[2] == 9  # typical_active_hour (every session starts at 9am)
        assert params[5] == 5  # sample_count
        mock_db.commit.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_skips_devices_below_minimum_sample_count(self, mock_connect):
        """A device with fewer than ENTITY_BASELINE_MIN_SAMPLES complete
        sessions must not get a baseline row -- too little history to be a
        real "typical" pattern yet."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        online_hour = datetime(2026, 8, 1, 9, 0)
        sessions = [
            (online_hour, "online"),
            (online_hour + timedelta(minutes=60), "offline"),
        ]
        mock_cursor.fetchall.side_effect = [[(42,)], sessions]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 0
        mock_db.commit.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_rolls_back_and_closes_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        compute_entity_baselines()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestCheckNowPlaying:
    """Tests for MyDaemon.check_now_playing()."""

    def _playback_state(self, track_id="track1", name="Song", artists=None, is_playing=True):
        return {
            "is_playing": is_playing,
            "item": {"id": track_id, "name": name, "artists": artists or ["Artist"]},
        }

    @patch("common.spotify_utils.get_playback_state")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_nothing_playing_returns_none_without_touching_db_or_producer(
        self, mock_connect, mock_producer, mock_playback
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_playback.return_value = {"is_playing": False, "item": None}

        daemon = MyDaemon()
        result = daemon.check_now_playing()

        assert result is None
        mock_connect.assert_not_called()
        mock_producer.assert_not_called()

    @patch("common.spotify_utils.get_playback_state")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_new_track_persists_state_and_publishes_event(
        self, mock_connect, mock_producer, mock_playback
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_playback.return_value = self._playback_state()

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # nothing persisted yet
        mock_cursor.rowcount = 1  # UPDATE "succeeds" -> no INSERT fallback

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing()

        assert card["mode"] == "music"
        assert card["track_title"] == "Song"
        assert card["track_artist"] == "Artist"
        assert card["is_playing"] is True

        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 1
        mock_p.send.assert_called_once()
        assert mock_p.send.call_args.args[0] == "event-stream"

    @patch("common.spotify_utils.get_playback_state")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_unchanged_track_does_not_rewrite_or_republish(
        self, mock_connect, mock_producer, mock_playback
    ):
        """Same track_id + is_playing as last cycle must not spam config writes
        or event-stream messages every ~60s poll."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_playback.return_value = self._playback_state(track_id="track1", is_playing=True)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (
            '{"track_id": "track1", "title": "Song", "artist": "Artist", "is_playing": true}',
        )

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing()

        assert card is not None
        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 0
        mock_p.send.assert_not_called()

    @patch("common.spotify_utils.get_playback_state")
    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_pause_transition_persists_state_but_returns_no_card(
        self, mock_connect, mock_producer, mock_playback
    ):
        """A track paused (item still present, is_playing False) must still
        get persisted to config -- check_cross_surface_continuity() depends
        on that "paused N minutes ago" state -- but produces no situational-
        awareness card and no event-stream announcement of its own."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_playback.return_value = self._playback_state(track_id="track1", is_playing=False)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (
            '{"track_id": "track1", "title": "Song", "artist": "Artist", "is_playing": true}',
        )
        mock_cursor.rowcount = 1

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing()

        assert card is None
        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 1
        mock_p.send.assert_not_called()

    @patch("common.spotify_utils.get_playback_state")
    def test_playback_lookup_error_is_caught_and_returns_none(self, mock_playback):
        """A Spotify/network error must not crash decide_displays() -- same
        graceful-degradation contract as the other DB/API-backed checks."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_playback.side_effect = Exception("network down")

        daemon = MyDaemon()
        result = daemon.check_now_playing()

        assert result is None


class TestCheckCrossSurfaceContinuity:
    """Tests for MyDaemon.check_cross_surface_continuity()."""

    @staticmethod
    def _config_row(minutes_ago, **fields):
        import json

        value = json.dumps(
            {
                **fields,
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
                ).isoformat(),
            }
        )
        return (value,)

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_offers_resume_for_a_recently_paused_track(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            self._config_row(4, track_id="track1", title="Song", is_playing=False),  # now_playing
            None,  # surface_state: nothing reported
            None,  # routines: none edited
        ]

        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity()

        assert result["mode"] == "cross_surface_continuity"
        assert result["resume_type"] == "music"
        assert result["resume_target"] == "track1"
        assert "Song" in result["content"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_ignores_a_paused_track_older_than_staleness_window(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            self._config_row(120, track_id="track1", title="Song", is_playing=False),
            None,
            None,
        ]

        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_picks_the_most_recent_of_multiple_candidates(self, mock_connect):
        """A terminal session reported 1 min ago must win over a track
        paused 10 min ago, even though the music check runs first."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            self._config_row(10, track_id="track1", title="Song", is_playing=False),
            self._config_row(1, terminal_session_active=True),
            None,
        ]

        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity()

        assert result["resume_type"] == "terminal"

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_nothing_available(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, None, None]

        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity()

        assert result is None


def _telemetry_row(minutes_ago, **fields):
    import json

    value = json.dumps(
        {
            **fields,
            "reported_at": (
                datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
            ).isoformat(),
        }
    )
    return (value,)


class TestCheckAttentionFocus:
    """Tests for MyDaemon.check_attention_focus()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_fires_when_switching_is_high_and_not_media_heavy(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5,
            switch_count=20,
            unlock_count=1,
            dwell_by_category_ms={"terminal": 600000, "media": 100000},
        )

        daemon = MyDaemon()
        result = daemon.check_attention_focus()

        assert result["mode"] == "attention_focus"
        assert result["priority"] == 3.6
        assert result["switch_count"] == 20

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_switch_count_is_low(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5, switch_count=3, dwell_by_category_ms={"terminal": 600000}
        )

        daemon = MyDaemon()
        result = daemon.check_attention_focus()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_switching_is_media_heavy(self, mock_connect):
        """High switch count while mostly dwelling in media is the wind-down
        pattern, not focus -- must not double-fire both cards."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5,
            switch_count=20,
            dwell_by_category_ms={"media": 800000, "terminal": 100000},
        )

        daemon = MyDaemon()
        result = daemon.check_attention_focus()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_snapshot_is_stale(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            120, switch_count=20, dwell_by_category_ms={"terminal": 600000}
        )

        daemon = MyDaemon()
        result = daemon.check_attention_focus()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_snapshot_reported_yet(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = MyDaemon()
        result = daemon.check_attention_focus()

        assert result is None


class TestCheckWindDownSignal:
    """Tests for MyDaemon.check_wind_down_signal()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_fires_when_night_and_high_unlocks_and_media_heavy(
        self, mock_get_local_time, mock_connect
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 28, 23, 30)  # night

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5,
            unlock_count=8,
            switch_count=2,
            dwell_by_category_ms={"media": 900000, "terminal": 50000},
        )

        daemon = MyDaemon()
        result = daemon.check_wind_down_signal()

        assert result["mode"] == "wind_down_signal"
        assert result["priority"] == 5.8
        assert result["unlock_count"] == 8

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_returns_none_when_not_night(self, mock_get_local_time, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 28, 14, 0)  # afternoon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5, unlock_count=8, dwell_by_category_ms={"media": 900000}
        )

        daemon = MyDaemon()
        result = daemon.check_wind_down_signal()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_returns_none_when_unlock_count_is_low(self, mock_get_local_time, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 28, 23, 30)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5, unlock_count=1, dwell_by_category_ms={"media": 900000}
        )

        daemon = MyDaemon()
        result = daemon.check_wind_down_signal()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_returns_none_when_dwell_is_not_media_heavy(self, mock_get_local_time, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 28, 23, 30)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(
            5,
            unlock_count=8,
            dwell_by_category_ms={"terminal": 900000, "media": 50000},
        )

        daemon = MyDaemon()
        result = daemon.check_wind_down_signal()

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_snapshot_reported_yet(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = MyDaemon()
        result = daemon.check_wind_down_signal()

        assert result is None


class TestFocusUtils:
    """Tests for focus_utils.looks_like_call()."""

    def test_zoom_url_matches(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call("https://us02web.zoom.us/j/123456", None) is True

    def test_meet_google_url_matches(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call(None, "Join here: https://meet.google.com/abc-defg-hij") is True

    def test_teams_url_matches(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call("https://teams.microsoft.com/l/meetup-join/xyz", None) is True

    def test_bare_zoom_mention_matches(self):
        """Organizers sometimes paste a friendly label instead of a raw URL."""
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call(None, "Quick Zoom to review the roadmap") is True

    def test_ordinary_address_and_notes_do_not_match(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call("123 Main St", "Bring snacks") is False

    def test_no_address_or_notes_does_not_match(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call(None, None) is False

    def test_matching_is_case_insensitive(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call(None, "ZOOM.US/j/999") is True
        assert looks_like_call(None, "Let's do a GOOGLE MEET") is True


class TestCheckFocusNeeded:
    """Tests for MyDaemon.check_focus_needed()."""

    @staticmethod
    def _make_event(minutes_from_now, address=None, notes=None, title="Standup"):
        return [
            {
                "title": title,
                "start_time": datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
                "address": address,
                "notes": notes,
            }
        ]

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_fires_when_call_like_and_within_lead_time(self, mock_get_events):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = self._make_event(
            5, address="https://zoom.us/j/123", title="1:1 with Bob"
        )

        daemon = MyDaemon()
        card = daemon.check_focus_needed()

        assert card is not None
        assert card["mode"] == "focus_needed"
        assert "1:1 with Bob" in card["content"]
        assert card["priority"] == 3.5

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_returns_none_when_outside_lead_time(self, mock_get_events):
        """Matches, but starts well beyond FOCUS_LEAD_MINUTES away."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = self._make_event(45, address="https://zoom.us/j/123")

        daemon = MyDaemon()
        assert daemon.check_focus_needed() is None

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_returns_none_when_event_does_not_look_like_call(self, mock_get_events):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = self._make_event(
            5, address="123 Main St", notes="Bring donuts"
        )

        daemon = MyDaemon()
        assert daemon.check_focus_needed() is None

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_returns_none_when_no_upcoming_event(self, mock_get_events):
        """Mirrors check_events()'s existing "no event" behavior."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = None

        daemon = MyDaemon()
        assert daemon.check_focus_needed() is None


class TestCheckEvents:
    """Regression tests for check_events(). A backend-computed travel/leave-by
    card (check_travel(), Google Maps Directions) briefly existed as a
    separate card but was removed -- it needed a paid Maps API tier the
    household isn't using. The "Open Maps" destination action now lives
    entirely client-side in alfr3d_deck's next_event_soon rule instead, so
    check_events() here only ever shows the plain title/time line."""

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_event_card_shows_plain_title_and_time(self, mock_get_events):
        """check_events() returns a well-formed card with no travel numbers and
        none of the old dead placeholder's dress/umbrella wording."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = [
            {
                "title": "Dentist",
                "start_time": datetime.now(timezone.utc) + timedelta(minutes=30),
                "address": "123 Main St",
                "notes": None,
            }
        ]

        daemon = MyDaemon()
        card = daemon.check_events()

        assert card is not None
        assert card["mode"] == "event"
        assert card["priority"] == 2
        assert "Dentist" in card["content"]
        for dead_text in (
            "Wear",
            "umbrella",
            "Bring umbrella",
            "jacket",
            "shorts",
            "Leave at",
            "Fuel:",
        ):
            assert dead_text not in card["content"]

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_returns_none_when_no_upcoming_event(self, mock_get_events):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = None

        daemon = MyDaemon()
        assert daemon.check_events() is None

    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    def test_returns_none_when_event_more_than_three_hours_out(self, mock_get_events):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_events.return_value = [
            {
                "title": "Dentist",
                "start_time": datetime.now(timezone.utc) + timedelta(hours=4),
                "address": "123 Main St",
                "notes": None,
            }
        ]

        daemon = MyDaemon()
        assert daemon.check_events() is None


class TestCheckWeatherAdvisory:
    """Tests for MyDaemon.check_weather_advisory()."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_fires_when_rain_probability_exceeds_threshold(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            RAIN_ADVISORY_THRESHOLD,
            FORECAST_HOURS_AHEAD,
        )

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (RAIN_ADVISORY_THRESHOLD + 10,)

        daemon = MyDaemon()
        card = daemon.check_weather_advisory()

        assert card is not None
        assert card["mode"] == "weather_advisory"
        assert card["priority"] == 4.5
        assert str(FORECAST_HOURS_AHEAD) in card["content"]
        assert "umbrella" in card["content"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_below_threshold(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            RAIN_ADVISORY_THRESHOLD,
        )

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (RAIN_ADVISORY_THRESHOLD - 5,)

        daemon = MyDaemon()
        assert daemon.check_weather_advisory() is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_forecast_not_yet_populated(self, mock_connect):
        """No forecast snapshot yet (NULL column) must not crash, just skip the card."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (None,)

        daemon = MyDaemon()
        assert daemon.check_weather_advisory() is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        """A DB failure must not crash decide_displays(), same as check_weather()."""
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_connect.side_effect = pymysql.err.OperationalError("db down")

        daemon = MyDaemon()
        assert daemon.check_weather_advisory() is None


class TestCheckTime:
    """Tests for MyDaemon.check_time() -- previously exercised only indirectly
    via decide_displays() stubs, never as its own real (unmocked) call."""

    def test_returns_well_formed_time_card(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        card = daemon.check_time()

        assert card["mode"] == "time"
        assert card["priority"] == 1
        # content is a real ISO-8601 timestamp, not a placeholder string.
        datetime.fromisoformat(card["content"])


class TestCheckWeather:
    """Tests for MyDaemon.check_weather() -- previously exercised only via
    decide_displays() stubs, never with a real DB-backed call."""

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_formatted_weather_card(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Testville", "clear", 10, 22, "pleasant")

        daemon = MyDaemon()
        card = daemon.check_weather()

        assert card == {
            "mode": "weather",
            "content": "Testville: pleasant, clear, 10°C to 22°C",
            "priority": 5,
        }
        mock_db.close.assert_called_once()

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_environment_row(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = MyDaemon()
        assert daemon.check_weather() is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        """A DB failure must not crash decide_displays(), same as the other checks."""
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_connect.side_effect = pymysql.err.OperationalError("db down")

        daemon = MyDaemon()
        assert daemon.check_weather() is None


class TestCheckEmails:
    """Tests for MyDaemon.check_emails() -- previously exercised only via
    decide_displays() stubs; gmail_utils.check_unread_emails() itself is a
    placeholder that always returns None, so the "emails found" branch of
    check_emails() had never actually run under test."""

    @patch("services.service_daemon.alfr3ddaemon.gmail_utils.check_unread_emails")
    def test_returns_card_summarizing_first_unread_email(self, mock_check_unread):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_check_unread.return_value = [
            {"sender": "boss@example.com", "subject": "Q3 numbers"},
            {"sender": "friend@example.com", "subject": "Lunch?"},
        ]

        daemon = MyDaemon()
        card = daemon.check_emails()

        assert card["mode"] == "email"
        assert card["priority"] == 4
        assert "boss@example.com" in card["content"]
        assert "Q3 numbers" in card["content"]
        assert "Total Unread: 2" in card["content"]

    @patch("services.service_daemon.alfr3ddaemon.gmail_utils.check_unread_emails")
    def test_returns_none_when_no_unread_emails(self, mock_check_unread):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_check_unread.return_value = None

        daemon = MyDaemon()
        assert daemon.check_emails() is None


class TestPublishSA:
    """Tests for MyDaemon.publish_sa()."""

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    def test_sends_data_to_situational_awareness_topic(self, mock_get_producer):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        daemon = MyDaemon()
        daemon.publish_sa([{"mode": "time", "content": "t", "priority": 1}])

        assert mock_producer.send.call_args[0][0] == "situational-awareness"

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    def test_no_crash_when_producer_unavailable(self, mock_get_producer):
        """No Kafka producer (e.g. broker unreachable) must not raise."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_producer.return_value = None

        daemon = MyDaemon()
        daemon.publish_sa([{"mode": "time", "content": "t", "priority": 1}])  # must not raise


class TestCheckSituationalAwareness:
    """Tests for MyDaemon.check_situational_awareness(), the orchestration
    method that ties decide_displays() and publish_sa() together."""

    def test_publishes_when_displays_are_returned(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        cards = [{"mode": "time", "content": "t", "priority": 1}]
        daemon.decide_displays = MagicMock(return_value=cards)
        daemon.publish_sa = MagicMock()

        daemon.check_situational_awareness()

        daemon.publish_sa.assert_called_once_with(cards)

    def test_does_not_publish_when_no_displays_fire(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        daemon.decide_displays = MagicMock(return_value=[])
        daemon.publish_sa = MagicMock()

        daemon.check_situational_awareness()

        daemon.publish_sa.assert_not_called()
