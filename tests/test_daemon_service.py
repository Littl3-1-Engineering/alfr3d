"""Tests for the ALFR3D daemon service utilities."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import orjson
import pytest


def _make_frame(**overrides):
    """Build a context_frame.ContextFrame test double (SA-4) with sensible defaults,
    overridden per test. `now` defaults to real current time since most rules only compare
    it against other supplied values, not an exact wall-clock string."""
    from services.service_daemon.utils.context_frame import ContextFrame

    frame = ContextFrame()
    frame.now = datetime.now(timezone.utc)
    for key, value in overrides.items():
        setattr(frame, key, value)
    return frame


def _make_launcher_context(**overrides):
    from services.service_daemon.utils.context_frame import LauncherContext

    launcher = LauncherContext()
    for key, value in overrides.items():
        setattr(launcher, key, value)
    return launcher


def _online_devices(rows):
    """Build a frame.online_devices value (SA-4) from raw (username, device_name) rows,
    mirroring context_frame.fetch_online_devices()'s own computation -- that function has
    its own dedicated tests (TestContextFrame), so callers here just need realistic input."""
    known_names = sorted({row[0] for row in rows if row[0]})
    return {
        "rows": rows,
        "known_names": known_names,
        "known_count": len(known_names),
        "unknown_count": sum(1 for row in rows if not row[0]),
    }


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
            "https://meet.google.com/abc-defg-hij",
            "Google Meet",
        )

        result = get_upcoming_events()

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Test Event"
        assert result[0]["address"] == "123 Main St"
        assert result[0]["notes"] == "Test notes"
        assert result[0]["conference_uri"] == "https://meet.google.com/abc-defg-hij"
        assert result[0]["conference_solution"] == "Google Meet"
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


class TestCalendarSync:
    """Tests for sync_calendar()'s before/after diff and event-stream
    publishing (SA-11 Phase 2). sync_calendar() deletes and re-inserts the
    whole sync window on every run, so these confirm a genuinely new/removed
    event is distinguished from one merely being re-synced unchanged."""

    @staticmethod
    def _google_event(title="Test Event", start="2026-08-30T10:00:00Z", end="2026-08-30T11:00:00Z"):
        return {
            "summary": title,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
            "location": "Home",
            "description": "desc",
        }

    def _mock_google_service(self, events):
        mock_service = MagicMock()
        mock_service.calendarList.return_value.list.return_value.execute.return_value = {
            "items": [{"summary": "Family", "id": "cal1"}]
        }
        mock_service.events.return_value.list.return_value.execute.return_value = {"items": events}
        return mock_service

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_publishes_created_event_for_a_genuinely_new_calendar_event(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        mock_build.return_value = self._mock_google_service([self._google_event()])

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []  # nothing existed before this sync

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        sync_calendar()

        mock_producer.send.assert_called_once()
        topic, payload = mock_producer.send.call_args.args
        assert topic == "event-stream"
        published = orjson.loads(payload)
        assert published["subject_type"] == "calendar_event"
        assert published["subject_id"] == "Test Event"
        assert published["verb"] == "created"

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_persists_conference_metadata_when_present(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """SA-7: an event with structured Google conferencing data gets its
        conference_uri/conference_solution persisted alongside the rest."""
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        event = self._google_event()
        event["conferenceData"] = {
            "conferenceSolution": {"name": "Google Meet"},
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
            ],
        }
        mock_build.return_value = self._mock_google_service([event])

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_get_producer.return_value = MagicMock()

        sync_calendar()

        insert_calls = [
            c
            for c in mock_cursor.execute.call_args_list
            if "INSERT INTO calendar_events" in c.args[0]
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0].args[1]
        assert params[5] == "https://meet.google.com/abc-defg-hij"
        assert params[6] == "Google Meet"

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_persists_null_conference_metadata_when_absent(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """An event with no conferencing data at all persists NULLs, not an
        error -- the common case today."""
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        mock_build.return_value = self._mock_google_service([self._google_event()])

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_get_producer.return_value = MagicMock()

        sync_calendar()

        insert_calls = [
            c
            for c in mock_cursor.execute.call_args_list
            if "INSERT INTO calendar_events" in c.args[0]
        ]
        params = insert_calls[0].args[1]
        assert params[5] is None
        assert params[6] is None

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_skips_publish_for_an_unchanged_calendar_event(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """The same event re-synced unchanged must not be reported as
        'created' -- that would spam an event for every event on every
        sync tick."""
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        mock_build.return_value = self._mock_google_service([self._google_event()])

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        # Exactly what this event will parse to -- already present before the sync.
        mock_cursor.fetchall.return_value = [
            (
                "Test Event",
                datetime(2026, 8, 30, 10, 0, 0),
                datetime(2026, 8, 30, 11, 0, 0),
                "Home",
                "desc",
            )
        ]

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        sync_calendar()

        mock_producer.send.assert_not_called()

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_before_snapshot_and_delete_filter_on_end_time_not_start_time(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """Regression test for a bug caught live: Google's timeMin/timeMax
        filter by end_time/start_time respectively, so an event already in
        progress (start in the past, end still ahead) keeps being returned
        by the API. A window filtered on `start_time >= now` on both ends
        would miss that row entirely -- leaving it un-deleted *and* outside
        the diff's "before" snapshot -- so it gets re-inserted as a
        duplicate and misreported as newly "created" on every sync while
        it's still running."""
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        mock_build.return_value = self._mock_google_service([self._google_event()])

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_get_producer.return_value = MagicMock()

        sync_calendar()

        select_call = next(
            c
            for c in mock_cursor.execute.call_args_list
            if c.args[0].strip().startswith("SELECT title")
        )
        delete_call = next(
            c
            for c in mock_cursor.execute.call_args_list
            if "DELETE FROM calendar_events" in c.args[0]
        )
        assert "end_time >= %s AND start_time <= %s" in select_call.args[0]
        assert "end_time >= %s AND start_time <= %s" in delete_call.args[0]

    @patch("services.service_daemon.utils.calendar_utils.get_producer")
    @patch("services.service_daemon.utils.calendar_utils.pymysql.connect")
    @patch("services.service_daemon.utils.calendar_utils.build")
    @patch("services.service_daemon.utils.calendar_utils.get_credentials")
    def test_publishes_removed_event_for_one_dropped_from_the_calendar(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        from services.service_daemon.utils.calendar_utils import sync_calendar

        mock_creds.return_value = MagicMock()
        mock_build.return_value = self._mock_google_service([])  # nothing upcoming anymore

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (
                "Cancelled Meeting",
                datetime(2026, 8, 30, 10, 0, 0),
                datetime(2026, 8, 30, 11, 0, 0),
                "Home",
                "desc",
            )
        ]

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        sync_calendar()

        mock_producer.send.assert_called_once()
        _topic, payload = mock_producer.send.call_args.args
        published = orjson.loads(payload)
        assert published["subject_id"] == "Cancelled Meeting"
        assert published["verb"] == "removed"


class TestExtractConferenceInfo:
    """Tests for calendar_utils._extract_conference_info() (SA-7)."""

    def test_returns_uri_and_solution_from_conference_data(self):
        from services.service_daemon.utils.calendar_utils import _extract_conference_info

        event = {
            "conferenceData": {
                "conferenceSolution": {"name": "Google Meet"},
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
                ],
            }
        }
        assert _extract_conference_info(event) == (
            "https://meet.google.com/abc-defg-hij",
            "Google Meet",
        )

    def test_prefers_the_video_entry_point_over_others(self):
        """conferenceData can list multiple entry points (video, phone, sip)
        -- the video one is what a "find a quiet spot" card cares about."""
        from services.service_daemon.utils.calendar_utils import _extract_conference_info

        event = {
            "conferenceData": {
                "conferenceSolution": {"name": "Zoom"},
                "entryPoints": [
                    {"entryPointType": "phone", "uri": "tel:+1-555-0100"},
                    {"entryPointType": "video", "uri": "https://zoom.us/j/123"},
                ],
            }
        }
        assert _extract_conference_info(event) == ("https://zoom.us/j/123", "Zoom")

    def test_falls_back_to_hangout_link_without_conference_data(self):
        event = {"hangoutLink": "https://meet.google.com/legacy-link"}
        from services.service_daemon.utils.calendar_utils import _extract_conference_info

        assert _extract_conference_info(event) == (
            "https://meet.google.com/legacy-link",
            "Google Meet",
        )

    def test_returns_none_none_when_neither_field_present(self):
        from services.service_daemon.utils.calendar_utils import _extract_conference_info

        assert _extract_conference_info({}) == (None, None)

    def test_returns_none_none_when_conference_data_has_no_entry_points(self):
        from services.service_daemon.utils.calendar_utils import _extract_conference_info

        event = {"conferenceData": {"conferenceSolution": {"name": "Zoom"}, "entryPoints": []}}
        assert _extract_conference_info(event) == (None, None)


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
        assert event["subject_type"] == "track"
        assert event["subject_id"] == "t1"
        assert event["verb"] == "play_start"

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
        assert event["subject_type"] == "track"
        assert event["verb"] == "play_stop"
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

    @pytest.fixture(autouse=True)
    def _no_card_interaction_history(self):
        """decide_displays() now builds a real ContextFrame (SA-4) at the top of every
        cycle and runs a suppression pass (SA-1) that queries card_interactions for
        every card. These tests only care about registry/sort/cap/suppression behavior
        given already-decided check_* results (all stubbed via _stub_daemon()), not
        about how the frame itself gets built -- so build_context_frame() is stubbed
        out entirely rather than mocking each of its individual DB/API dependencies.

        That's not just tidiness: mocking only pymysql.connect here still let a real
        db_utils.get_env_local_time() call through (build_context_frame() calls it
        directly, unconditionally) reach services.common.db_pool's process-global
        connection pool. That pool eagerly creates its `mincached` connections via
        whatever `pymysql.connect` is bound to *at the moment it's first constructed*
        and caches them for the rest of the pytest process -- so the first test here
        to run permanently poisoned the pool with mock connections, breaking unrelated
        tests in *other* test files (test_personality.py) later in the same session.
        Suppression itself (the pymysql.connect mock below, for
        _card_suppression_reason()'s own direct per-card queries) is covered by its
        own TestCardSuppression class.
        """
        from services.service_daemon.utils.context_frame import ContextFrame

        with patch(
            "services.service_daemon.alfr3ddaemon.MyDaemon.build_context_frame"
        ) as mock_build, patch(
            "services.service_daemon.alfr3ddaemon.pymysql.connect"
        ) as mock_connect:
            mock_build.return_value = ContextFrame()
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            yield

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
    EMPTY_HOUSE_STILL_ON_CARD = {
        "mode": "empty_house_still_on",
        "content": "House appears empty, but Living Room Lamp still on",
        "priority": 2.4,
        "device_count": 1,
    }
    DEPARTURE_ANOMALY_CARD = {
        "mode": "departure_anomaly",
        "content": "Munja still home — unusual for a Tuesday",
        "priority": 2.7,
        "entity_name": "Munja",
        "data": {"typical_departure_hour": 8, "sample_count": 12, "because": ["..."]},
    }
    TRAVEL_CARD = {
        "mode": "travel",
        "content": "Leave by 05:10 PM for Dentist",
        "priority": 2.5,
        "data": {
            "duration_minutes": 20,
            "distance_km": 12.3,
            "traffic_aware": False,
            "leave_by": "2026-08-11T17:10:00+00:00",
            "because": ["20 min drive to Dentist"],
        },
    }
    HOUSEHOLD_UNUSUAL_DAY_CARD = {
        "mode": "household_unusual_day",
        "content": "Tuesday is running differently than usual",
        "priority": 6.5,
        "data": {
            "today_device_count": 2,
            "typical_device_count_range": [5, 10],
            "today_first_activity_hour": 11,
            "typical_first_activity_hour": 7,
            "because": ["...", "..."],
        },
    }

    def _stub_daemon(
        self,
        check_time=None,
        check_events=None,
        check_travel=None,
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
        check_empty_house_still_on=None,
        check_departure_anomaly=None,
        check_household_unusual_day=None,
    ):
        """Build a MyDaemon with each check_* replaced by a stub returning the given card."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        daemon.check_time = MagicMock(return_value=check_time)
        daemon.check_events = MagicMock(return_value=check_events)
        daemon.check_travel = MagicMock(return_value=check_travel)
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
        daemon.check_empty_house_still_on = MagicMock(return_value=check_empty_house_still_on)
        daemon.check_departure_anomaly = MagicMock(return_value=check_departure_anomaly)
        daemon.check_household_unusual_day = MagicMock(return_value=check_household_unusual_day)
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
            check_empty_house_still_on=self.EMPTY_HOUSE_STILL_ON_CARD,
            check_departure_anomaly=self.DEPARTURE_ANOMALY_CARD,
            check_travel=self.TRAVEL_CARD,
            check_household_unusual_day=self.HOUSEHOLD_UNUSUAL_DAY_CARD,
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
        assert self.EMPTY_HOUSE_STILL_ON_CARD in result

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
        (all sixteen DISPLAY_RULES entries) firing at once.

        This is the test to extend when a future PR registers another category:
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
            check_empty_house_still_on=self.EMPTY_HOUSE_STILL_ON_CARD,
            check_departure_anomaly=self.DEPARTURE_ANOMALY_CARD,
            check_travel=self.TRAVEL_CARD,
            check_household_unusual_day=self.HOUSEHOLD_UNUSUAL_DAY_CARD,
        )

        result = daemon.decide_displays()

        # Sorted ascending by priority.
        priorities = [card["priority"] for card in result]
        assert priorities == sorted(priorities)

        # Cap behavior: MAX_DISPLAYS == len(DISPLAY_RULES), and every registered
        # rule fired exactly once, so all nineteen cards come back -- nothing dropped.
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert len(result) == 19 == MyDaemon.MAX_DISPLAYS == len(MyDaemon.DISPLAY_RULES)

        # No two cards silently collide on priority value.
        # (music and now_playing intentionally share mode "music" at different
        # priorities -- 3 vs 3.1 -- so they don't collide on priority either.)
        assert len(priorities) == len(set(priorities))

        assert [card["mode"] for card in result] == [
            "time",
            "event",
            "empty_house_still_on",
            "travel",
            "rhythm_break_anomaly",
            "departure_anomaly",
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
            "household_unusual_day",
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


class TestCardSuppression(TestDecideDisplays):
    """Tests for MyDaemon._card_subject_key()/_card_suppression_reason() and
    decide_displays()'s suppression pass (SA-1). Inherits TestDecideDisplays'
    autouse "no history yet" pymysql.connect stub, CARD constants, and
    _stub_daemon() helper; individual tests re-patch pymysql.connect to
    exercise specific interaction histories."""

    def test_published_cards_are_stamped_with_rule_id_and_subject_key(self):
        """Consumers (React dashboard, Nexus Launcher) need a reliable card
        identity to report shown/tapped/dismissed against -- the card's own
        "mode" field isn't it (music/now_playing collide), so
        decide_displays() must stamp the real identity onto every card it
        returns."""
        daemon = self._stub_daemon(
            check_weather=self.WEATHER_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
        )

        result = daemon.decide_displays()

        by_mode = {card["mode"]: card for card in result}
        assert by_mode["weather"]["rule_id"] == "weather"
        assert by_mode["weather"]["subject_key"] == ""
        assert by_mode["rhythm_break_anomaly"]["rule_id"] == "rhythm_break_anomaly"
        assert by_mode["rhythm_break_anomaly"]["subject_key"] == "Garage light"

    def test_subject_key_is_empty_for_singleton_rules(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert MyDaemon._card_subject_key("weather", self.WEATHER_CARD) == ""

    def test_subject_key_uses_entity_name_for_rhythm_break_anomaly(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert (
            MyDaemon._card_subject_key("rhythm_break_anomaly", self.RHYTHM_BREAK_ANOMALY_CARD)
            == "Garage light"
        )

    def test_subject_key_uses_entity_name_for_departure_anomaly(self):
        """SA-3's departure_anomaly is rhythm_break_anomaly's human analogue -- dismissing
        one resident's card must not suppress a different resident's."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert (
            MyDaemon._card_subject_key("departure_anomaly", self.DEPARTURE_ANOMALY_CARD) == "Munja"
        )

    def test_subject_key_combines_resume_type_and_target_for_cross_surface_continuity(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert (
            MyDaemon._card_subject_key(
                "cross_surface_continuity", self.CROSS_SURFACE_CONTINUITY_CARD
            )
            == "music:track1"
        )

    def test_suppression_reason_is_none_with_no_history(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert MyDaemon()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_cooldown_right_after_a_dismissal(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))
            ]

            assert MyDaemon()._card_suppression_reason("weather", "") == "cooldown"

    def test_suppression_reason_is_none_once_cooldown_has_elapsed(self):
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES,
        )

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            old = datetime.now(timezone.utc) - timedelta(
                minutes=CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES + 5
            )
            mock_cursor.fetchall.return_value = [("dismissed", old.replace(tzinfo=None))]

            assert MyDaemon()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_repetition_after_enough_unacknowledged_shows(self):
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES,
        )

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mock_cursor.fetchall.return_value = [
                ("shown", now)
            ] * CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES

            assert MyDaemon()._card_suppression_reason("weather", "") == "repetition"

    def test_suppression_reason_is_none_below_repetition_threshold(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mock_cursor.fetchall.return_value = [("shown", now)] * 3

            assert MyDaemon()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_a_tap_resets_the_repetition_run(self):
        """A 'tapped' interaction mixed into recent history breaks the
        consecutive-shown run -- only the unbroken run since the most recent
        non-'shown' action counts, even though the total 'shown' count across
        all returned rows exceeds the threshold."""
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES,
        )

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            rows = (
                [("shown", now)] * 3
                + [("tapped", now)]
                + [("shown", now)] * CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES
            )
            mock_cursor.fetchall.return_value = rows

            assert MyDaemon()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_none_on_db_error(self):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

            assert MyDaemon()._card_suppression_reason("weather", "") is None

    def test_dismissed_card_does_not_reappear_next_cycle(self):
        """decide_displays()-level integration: a card whose identity was just
        dismissed is dropped entirely, not just flagged."""
        daemon = self._stub_daemon(check_weather=self.WEATHER_CARD)

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))
            ]

            result = daemon.decide_displays()

        assert result == []

    def test_urgent_household_composition_card_is_never_suppressed(self):
        """Explicit acceptance-criteria test: a security-relevant card
        (household_composition's elevated/`urgent` variant) must show even
        with a fresh dismissal on record -- and card_interactions must not
        even be queried for it, since the override short-circuits before
        any suppression check. (build_context_frame() still makes its own,
        unrelated real queries on this same shared cursor -- filtered out
        below rather than asserting no query happened at all.)"""
        urgent_card = dict(self.HOUSEHOLD_COMPOSITION_CARD, priority=2.3, urgent=True)
        daemon = self._stub_daemon(check_household_composition=urgent_card)

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))
            ]

            result = daemon.decide_displays()

        assert result == [urgent_card]
        card_interaction_queries = [
            c for c in mock_cursor.execute.call_args_list if "card_interactions" in c.args[0]
        ]
        assert card_interaction_queries == []

    def test_ambient_household_composition_card_can_still_be_suppressed(self):
        """Only the urgent variant is exempt -- the ambient
        (urgent=False) household_composition card follows normal
        suppression rules like anything else."""
        ambient_card = dict(self.HOUSEHOLD_COMPOSITION_CARD, urgent=False)
        daemon = self._stub_daemon(check_household_composition=ambient_card)

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))
            ]

            result = daemon.decide_displays()

        assert result == []

    def test_different_rhythm_break_anomaly_entities_have_independent_suppression(self):
        """Dismissing one device's rhythm-break card must not suppress a
        different device's -- proves subject_key actually scopes the query,
        not just rule_id."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        def fetchall_by_subject_key(*args, **_kwargs):
            _rule_id, subject_key, _limit = args
            if subject_key == "Garage light":
                return [("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))]
            return []  # "Kitchen light" has no history at all

        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.side_effect = lambda: fetchall_by_subject_key(
                *mock_cursor.execute.call_args.args[1]
            )

            daemon = MyDaemon()
            assert daemon._card_suppression_reason("rhythm_break_anomaly", "Garage light") == (
                "cooldown"
            )
            assert daemon._card_suppression_reason("rhythm_break_anomaly", "Kitchen light") is None


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


def _frame_with_day_mood(local_dt):
    """frame.day_mood (SA-4) built from the real mood_utils.get_day_mood(), so tests still
    exercise the real bucket logic rather than hand-crafting the dict."""
    from services.service_daemon.utils.mood_utils import get_day_mood

    return _make_frame(local_dt=local_dt, day_mood=get_day_mood(local_dt))


class TestCheckMood:
    """Tests for MyDaemon.check_mood(). frame.day_mood (SA-4) replaces this rule's own
    get_env_local_time()/get_day_mood() calls."""

    def test_returns_well_formed_mood_card(self):
        """check_mood() returns a well-formed card with a non-empty content string."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))  # Tuesday evening
        daemon = MyDaemon()
        card = daemon.check_mood(frame)

        assert card["mode"] == "mood"
        assert isinstance(card["content"], str) and card["content"]
        assert card["priority"] == 6
        assert card["data"]["day_of_week"] == "Tuesday"
        assert card["data"]["time_of_day"] == "evening"
        assert isinstance(card["data"]["energy"], float)
        # Priority must not collide with any other registered rule.
        other_priorities = {
            priority for rule_id, priority, _ in MyDaemon.DISPLAY_RULES if rule_id != "mood"
        }
        assert card["priority"] not in other_priorities

    def test_low_energy_label_at_night(self):
        """Night baseline energy (0.30) must land in the 'low energy' bucket."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 2, 0))  # Tuesday 2am
        daemon = MyDaemon()
        card = daemon.check_mood(frame)

        assert "low energy" in card["content"]

    def test_high_energy_label_on_saturday_evening(self):
        """Weekend-bonus energy (0.70) must land in the 'high energy' bucket."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 15, 19, 0))  # Saturday evening
        daemon = MyDaemon()
        card = daemon.check_mood(frame)

        assert "high energy" in card["content"]

    def test_returns_none_when_day_mood_is_none(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_mood(_make_frame(day_mood=None)) is None


class TestCheckGatherings:
    """Regression tests for check_gatherings()'s time_of_day wiring after mood_utils
    extraction. frame.local_dt/frame.day_mood/frame.environment (SA-4) replace this rule's
    own get_env_local_time()/get_day_mood() calls and its own environment-table read --
    only the guest/total online-count query is still its own pymysql.connect() call."""

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_morning_gathering_passes_morning_time_of_day_to_recommend(
        self,
        mock_connect,
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

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 9, 0))  # Tuesday 9am
        frame.environment = {"description": "Clear", "subjective_feel": "Nice"}

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (2, 5)  # guest_count, total_count
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
        daemon.check_gatherings(frame)

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
        result = daemon.check_gatherings(_make_frame())

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_resolved_playlist_fields_are_attached_to_the_card(
        self,
        mock_connect,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """When spotify_utils.resolve_playlist() finds a real playlist, its
        fields (id/name/uri/url/image/source) must land on the returned card
        -- this is what the frontend's playlist-link rendering depends on."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))
        frame.environment = {"description": "Clear", "subjective_feel": "Nice"}

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (2, 5)
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
        card = daemon.check_gatherings(frame)

        assert card["playlist_id"] == "abc123"
        assert card["playlist_name"] == "Indie Chill"
        assert card["playlist_uri"] == "spotify:playlist:abc123"
        assert card["playlist_url"] == "https://open.spotify.com/playlist/abc123"
        assert card["playlist_image"] == "https://img.example.com/abc123.jpg"
        assert card["playlist_source"] == "search"
        assert card["data"]["mood"] == "warm indie"
        assert card["data"]["genre"] == "indie"
        assert card["data"]["energy"] == 0.5
        assert card["data"]["guest_count"] == 2
        assert card["data"]["total_count"] == 5
        assert card["data"]["because"]
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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_guest_and_total_count_are_plain_ints_not_decimal(
        self,
        mock_connect,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """Real regression, caught live: MySQL's SUM() (used for guest_count, unlike
        total_count's COUNT()) returns decimal.Decimal via pymysql. Before SA-5 that was fine
        -- guest_count only ever got interpolated into an f-string. Once SA-5 started putting
        it directly into the card's "data" dict for JSON publishing, an unconverted Decimal
        broke orjson.dumps() on the very first live cycle with a real gathering. Card fields
        must be plain int so json/orjson serialization never chokes on them."""
        from decimal import Decimal

        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))
        frame.environment = {"description": "Clear", "subjective_feel": "Nice"}

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (Decimal("2"), 5)
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
        card = daemon.check_gatherings(frame)

        assert type(card["data"]["guest_count"]) is int
        assert type(card["data"]["total_count"]) is int
        assert card["data"]["guest_count"] == 2

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_publishes_event_stream_message_when_producer_available(
        self,
        mock_connect,
        mock_get_producer,
        mock_recommend,
        mock_resolve,
    ):
        """A gathering-detected event is published to the event-stream topic
        when a Kafka producer is available."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))
        frame.environment = {"description": "Clear", "subjective_feel": "Nice"}

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (2, 5)
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
        daemon.check_gatherings(frame)

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
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_playlist_resolution_exception_falls_back_to_text_hint(
        self,
        mock_connect,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """resolve_playlist() raising must not crash check_gatherings() --
        it falls back to the plain text hint, with no playlist_* fields."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))
        frame.environment = {"description": "Clear", "subjective_feel": "Nice"}

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (2, 5)
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
        card = daemon.check_gatherings(frame)

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
        result = daemon.check_gatherings(_make_frame())

        assert result is None


class TestCheckHouseholdComposition:
    """Tests for MyDaemon.check_household_composition(). frame.online_devices (SA-4)
    replaces this rule's own device/state/user query -- check_empty_house_still_on() reads
    the same fetch."""

    def test_all_online_devices_claimed_is_ambient_priority(self):
        """Every online device belongs to a known household member -- low-urgency
        ambient card, same priority tier as mood."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices(
                [("athos", "Athos's Phone"), ("athos", "Athos's Laptop")]
            )
        )
        result = MyDaemon().check_household_composition(frame)

        assert result["mode"] == "household_composition"
        assert result["priority"] == 6.2
        assert result["urgent"] is False
        assert result["known_count"] == 1
        assert result["unknown_count"] == 0
        assert result["data"]["known_names"] == ["athos"]

    def test_unclaimed_device_online_is_elevated_priority(self):
        """An unclaimed/unknown MAC on the network -- elevated, security-relevant
        priority regardless of how many known members are also home."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices([("athos", "Athos's Phone"), (None, "Unclaimed Device")])
        )
        result = MyDaemon().check_household_composition(frame)

        assert result["priority"] == 2.3
        assert result["urgent"] is True
        assert result["known_count"] == 1
        assert result["unknown_count"] == 1

    def test_returns_none_when_no_devices_online(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(online_devices=_online_devices([]))
        result = MyDaemon().check_household_composition(frame)

        assert result is None

    def test_returns_none_when_frame_field_is_none(self):
        """frame.online_devices is None on a DB error building the frame -- must not crash."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        result = MyDaemon().check_household_composition(_make_frame(online_devices=None))

        assert result is None


class TestCheckRhythmBreakAnomaly:
    """Tests for MyDaemon.check_rhythm_break_anomaly() -- not a frame field (SA-4), this
    device/entity_baselines join isn't duplicated elsewhere, so it stays its own query;
    only frame.now replaces its own datetime.now(timezone.utc) call."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_card_when_a_device_is_past_its_typical_max(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Garage light", 90, 60)

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["priority"] == 2.6
        assert result["entity_name"] == "Garage light"
        assert result["deviation_type"] == "still_on_past_typical"
        assert "30 min" in result["content"]
        assert result["data"]["over_by_minutes"] == 30
        assert result["data"]["typical_daily_max_minutes"] == 60

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_device_exceeds_its_baseline(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_unusual_hour_card_when_no_still_on_deviation_but_hour_is_off(
        self, mock_connect
    ):
        """SA-10: second query (unusual_hour) is only reached once the first (still_on_past_
        typical) comes back empty."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, ("Garage light", 3, 15, 12)]

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["deviation_type"] == "unusual_hour"
        assert result["entity_name"] == "Garage light"
        assert result["data"]["current_hour"] == 3
        assert result["data"]["typical_active_hour"] == 15

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_expected_absent_card_when_neither_prior_deviation_fires(self, mock_connect):
        """SA-10: third query (expected_absent) is only reached once both prior queries come
        back empty."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, None, ("Coffee maker", 8, 7)]

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["deviation_type"] == "expected_absent"
        assert result["entity_name"] == "Coffee maker"
        assert result["data"]["typical_active_hour"] == 7
        assert "hasn't come online" in result["content"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_all_three_deviation_queries_come_back_empty(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, None, None]

        daemon = MyDaemon()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

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
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result is None
        mock_db.close.assert_called_once()


def _dense(start, end, step_minutes=5):
    """A device_history-style timestamp list at a fixed interval -- simulates a claimed
    device being seen every cycle for a stretch, the "still home, no gap" baseline every
    _departure_hours_by_bucket() test builds around."""
    timestamps = []
    current = start
    while current <= end:
        timestamps.append(current)
        current += timedelta(minutes=step_minutes)
    return timestamps


class TestDepartureHoursByBucket:
    """Tests for _departure_hours_by_bucket() (SA-3) -- the union-of-claimed-devices gap
    reduction check_departure_anomaly()'s baseline depends on. See its own doc comment for
    why this reads timestamp gaps rather than device_history's state column."""

    def test_records_departure_hour_from_the_last_row_before_a_real_gap(self):
        from services.service_daemon.alfr3ddaemon import _departure_hours_by_bucket

        day = datetime(2026, 8, 3)  # any calendar day; bucket assertion uses .weekday()
        timestamps = _dense(day.replace(hour=2), day.replace(hour=6, minute=30)) + [
            day.replace(hour=20)
        ]

        buckets = _departure_hours_by_bucket(timestamps)

        expected_bucket = "weekend" if day.weekday() >= 5 else "weekday"
        other_bucket = "weekday" if expected_bucket == "weekend" else "weekend"
        assert buckets[expected_bucket] == [6]
        assert buckets[other_bucket] == []

    def test_skips_a_day_with_no_overnight_confirmation(self):
        """If the first row seen on a calendar day is already past 05:00, that day's
        "departure" could just be a late-morning reappearance of an absence that started the
        night before -- must not be misattributed to this day."""
        from services.service_daemon.alfr3ddaemon import _departure_hours_by_bucket

        day = datetime(2026, 8, 3)
        timestamps = _dense(day.replace(hour=8), day.replace(hour=8, minute=30)) + [
            day.replace(hour=20)
        ]

        buckets = _departure_hours_by_bucket(timestamps)

        assert buckets["weekday"] == []
        assert buckets["weekend"] == []

    def test_a_short_gap_under_the_threshold_is_not_a_departure(self):
        """A blip under DEPARTURE_GAP_MINUTES (scan jitter/wifi power-saving, not a real
        absence) must not register as a departure -- scanning continues past it."""
        from services.service_daemon.alfr3ddaemon import _departure_hours_by_bucket

        day = datetime(2026, 8, 3)
        timestamps = (
            _dense(day.replace(hour=2), day.replace(hour=6))
            + [day.replace(hour=6, minute=20)]  # 20 min gap -- under the 31 min threshold
            + _dense(day.replace(hour=6, minute=25), day.replace(hour=9))
            + [day.replace(hour=20)]  # the real, later departure
        )

        buckets = _departure_hours_by_bucket(timestamps)

        expected_bucket = "weekend" if day.weekday() >= 5 else "weekday"
        assert buckets[expected_bucket] == [9]

    def test_fewer_than_two_timestamps_returns_empty_buckets(self):
        from services.service_daemon.alfr3ddaemon import _departure_hours_by_bucket

        assert _departure_hours_by_bucket([]) == {"weekday": [], "weekend": []}
        assert _departure_hours_by_bucket([datetime(2026, 8, 3, 6, 0)]) == {
            "weekday": [],
            "weekend": [],
        }

    def test_aggregates_multiple_days_into_the_right_bucket(self):
        from services.service_daemon.alfr3ddaemon import _departure_hours_by_bucket

        timestamps = []
        for day_offset in range(7):  # a full week, so both buckets get real samples
            day = datetime(2026, 8, 3) + timedelta(days=day_offset)
            timestamps += _dense(day.replace(hour=2), day.replace(hour=7))
            timestamps.append(day.replace(hour=22))  # a same-day, unambiguous return

        buckets = _departure_hours_by_bucket(timestamps)

        assert len(buckets["weekday"]) == 5
        assert len(buckets["weekend"]) == 2
        assert all(hour == 7 for hour in buckets["weekday"] + buckets["weekend"])


class TestComputeEntityBaselines:
    """Tests for compute_entity_baselines()."""

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_upserts_a_baseline_from_reconstructed_sessions(self, mock_connect, mock_tz):
        """Three online->offline pairs for one device should produce one
        upsert with the median/typical-hour/min/max derived from those
        three sessions, and a commit."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

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
        # 3rd/4th/5th fetchall(): SA-3's eligible-residents query (none eligible), then
        # SA-10's household aggregate query (no rows).
        mock_cursor.fetchall.side_effect = [[(42,)], sessions, [], []]

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

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_skips_devices_below_minimum_sample_count(self, mock_connect, mock_tz):
        """A device with fewer than ENTITY_BASELINE_MIN_SAMPLES complete
        sessions must not get a baseline row -- too little history to be a
        real "typical" pattern yet."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        online_hour = datetime(2026, 8, 1, 9, 0)
        sessions = [
            (online_hour, "online"),
            (online_hour + timedelta(minutes=60), "offline"),
        ]
        mock_cursor.fetchall.side_effect = [[(42,)], sessions, [], []]

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


class TestComputeUserDepartureBaselines:
    """Tests for compute_entity_baselines()'s SA-3 addition: entity_type='user' rows built
    from _departure_hours_by_bucket(), sharing the same table/cadence as the device baselines
    tested above. See todo/todo_departure_anomaly.md for the Phase 0 spike behind this."""

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_upserts_a_bucket_that_clears_the_floor_and_skips_one_that_doesnt(
        self, mock_connect, mock_tz
    ):
        """14 consecutive days -> 10 weekday departures (clears the 8-sample floor) and 4
        weekend departures (doesn't) -- weekday should get a row, weekend should not."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        timestamps = []
        start = datetime(2026, 8, 3)  # any date; the test only cares about weekday vs weekend
        for day_offset in range(14):
            day = start + timedelta(days=day_offset)
            timestamps += _dense(day.replace(hour=2), day.replace(hour=7))
            timestamps.append(day.replace(hour=22))
        timestamp_rows = [(ts,) for ts in timestamps]

        mock_cursor.fetchall.side_effect = [
            [],  # device_history distinct device_id scan (no device baselines this test)
            [(7, "Munja")],  # eligible non-guest residents with a claimed device
            [(89,), (128,)],  # Munja's claimed device ids
            timestamp_rows,  # union device_history timestamps for those device ids
            [],  # SA-10 household aggregate query
        ]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 1
        params = upsert_calls[0].args[1]
        assert params[0] == 7  # user_id
        assert params[1] == "weekday"
        assert params[2] == 7  # typical_active_hour (every departure at hour 7)
        assert params[3] == 7  # typical_daily_min
        assert params[4] == 7  # typical_daily_max
        assert params[5] == 10  # sample_count
        mock_db.commit.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_excludes_guests_from_the_eligible_residents_query(self, mock_connect, mock_tz):
        """The eligible-residents query itself (not a post-filter) must scope to
        owner/technoking/resident -- guests never even reach the departure computation. This
        test only asserts the query text, since the mocked cursor can't enforce real SQL
        filtering."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0
        mock_cursor.fetchall.side_effect = [[], [], []]

        compute_entity_baselines()

        eligible_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "FROM user u" in call.args[0] and "JOIN user_types ut" in call.args[0]
        ]
        assert len(eligible_calls) == 1
        assert "'owner', 'technoking', 'resident'" in eligible_calls[0].args[0]

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_skips_a_user_with_no_claimed_devices(self, mock_connect, mock_tz):
        """An eligible (non-guest) user with zero rows in `device` must be skipped cleanly,
        not crash on an empty device_ids list."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0
        mock_cursor.fetchall.side_effect = [
            [],
            [(7, "Munja")],
            [],  # no claimed devices for this user
            [],  # SA-10 household aggregate query
        ]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 0
        mock_db.commit.assert_called_once()


class TestComputeHouseholdBaselines:
    """Tests for compute_entity_baselines()'s SA-10 addition: entity_type='household' rows,
    computed as a single SQL aggregate rather than a per-entity Python loop -- see
    todo/todo_generalize_entity_baselines.md for the real production-hardware timing that
    motivated keeping it that way."""

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_upserts_household_baselines_for_both_buckets(self, mock_connect, mock_tz):
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        # (local_dow, first_hour, last_hour, device_count); MySQL DAYOFWEEK: 1=Sun...7=Sat.
        household_rows = [(2, 7, 22, 5)] * 15 + [  # 15 Mondays: weekday bucket
            (1, 9, 23, 3)
        ] * 15  # 15 Sundays: weekend bucket
        mock_cursor.fetchall.side_effect = [[], [], household_rows]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 2
        by_bucket = {call.args[1][1]: call.args[1] for call in upsert_calls}
        weekday_params = by_bucket["weekday"]
        assert weekday_params[0] == 0  # HOUSEHOLD_BASELINE_ENTITY_ID
        assert weekday_params[2] == 7  # typical_active_hour (first-activity)
        assert weekday_params[3] == 22  # typical_last_activity_hour
        assert weekday_params[4] == 5  # typical_daily_min
        assert weekday_params[5] == 5  # typical_daily_max
        assert weekday_params[6] == 15  # sample_count
        weekend_params = by_bucket["weekend"]
        assert weekend_params[2] == 9
        assert weekend_params[3] == 23

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_skips_a_bucket_below_the_sample_floor(self, mock_connect, mock_tz):
        from services.service_daemon.alfr3ddaemon import (
            HOUSEHOLD_BASELINE_MIN_SAMPLES,
            compute_entity_baselines,
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        household_rows = [(2, 7, 22, 5)] * (HOUSEHOLD_BASELINE_MIN_SAMPLES - 1)
        mock_cursor.fetchall.side_effect = [[], [], household_rows]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 0
        mock_db.commit.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_timezone")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_household_aggregate_is_a_single_query_not_a_per_entity_loop(
        self, mock_connect, mock_tz
    ):
        """The whole point of computing this as a GROUP BY aggregate instead of a per-device
        Python loop -- confirm exactly one execute() call touches device_history for the
        household block, regardless of how many days of history exist."""
        from services.service_daemon.alfr3ddaemon import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0
        mock_cursor.fetchall.side_effect = [[], [], [(2, 7, 22, 5)] * 20]

        compute_entity_baselines()

        household_query_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "GROUP BY local_date" in call.args[0]
        ]
        assert len(household_query_calls) == 1


class TestCheckDepartureAnomaly:
    """Tests for MyDaemon.check_departure_anomaly() (SA-3). Not a frame field -- this
    entity_baselines/device/calendar_events join isn't duplicated elsewhere, so it stays its
    own query; only frame.local_dt/frame.day_mood/frame.now are shared."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_fires_when_overdue_home_and_no_calendar_event_explains_it(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]  # id, name, typical_hour, n
        mock_cursor.fetchone.side_effect = [(1,), None]  # online_count=1, no calendar event

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))  # Tuesday 3pm
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card["mode"] == "departure_anomaly"
        assert card["priority"] == 2.7
        assert card["entity_name"] == "Munja"
        assert "Munja" in card["content"]
        assert "Tuesday" in card["content"]
        assert card["data"]["typical_departure_hour"] == 8
        assert card["data"]["sample_count"] == 12
        assert card["data"]["because"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_baseline_candidates(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_cursor.fetchone.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_before_the_grace_window_has_elapsed(self, mock_connect):
        """A resident whose current local hour hasn't yet cleared
        typical_hour + DEPARTURE_ANOMALY_GRACE_HOURS isn't overdue -- must not even reach the
        online-status check for that candidate."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 9, 0))  # only 1hr past typical_hour
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_cursor.fetchone.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_resident_is_not_currently_home(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]
        mock_cursor.fetchone.return_value = (0,)  # no claimed device online

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_a_calendar_event_covers_right_now(self, mock_connect):
        """A booked morning at home (e.g. WFH) is not a deviation -- must not fire even
        though the resident is overdue and home."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]
        mock_cursor.fetchone.side_effect = [(1,), ("Working from home",)]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_picks_the_most_overdue_resident_when_several_qualify(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        # Munja: 15:00 - 8:00 = 7h overdue. Vanja: 15:00 - 6:00 = 9h overdue -- more overdue.
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12), (9, "Vanja", 6, 10)]
        mock_cursor.fetchone.side_effect = [(1,), (1,), None]  # both home, no calendar event

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card["entity_name"] == "Vanja"

    def test_returns_none_when_frame_is_missing_local_dt_or_day_mood(self):
        """No DB connection should even be attempted without frame.local_dt/day_mood."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            assert daemon.check_departure_anomaly(_make_frame(local_dt=None, day_mood=None)) is None
            mock_connect.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = MyDaemon()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_db.close.assert_called_once()


class TestCheckHouseholdUnusualDay:
    """Tests for MyDaemon.check_household_unusual_day() (SA-10 Phase 3). Not a frame field --
    this entity_baselines/device_history join isn't duplicated elsewhere, so it stays its own
    query; only frame.local_dt/frame.day_mood/frame.now are shared."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_fires_when_both_count_and_hour_deviate_and_day_is_over(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        # typical_active_hour=7, typical_last_activity_hour=20, range=[5,10], sample_count=20,
        # min_sample_count=14.
        mock_cursor.fetchone.side_effect = [
            (7, 20, 5, 10, 20, 14),
            (11, 2),  # today: first activity at 11:00 (vs typical 7), only 2 devices (vs 5-10)
        ]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))  # Tuesday 9pm, past 20:00
        daemon = MyDaemon()
        card = daemon.check_household_unusual_day(frame)

        assert card is not None
        assert card["mode"] == "household_unusual_day"
        assert card["priority"] == 6.5
        assert "Tuesday" in card["content"]
        assert card["data"]["today_device_count"] == 2
        assert card["data"]["today_first_activity_hour"] == 11
        assert card["data"]["because"]

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_household_baseline_exists(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))
        daemon = MyDaemon()
        assert daemon.check_household_unusual_day(frame) is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_below_the_sample_floor(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (7, 20, 5, 10, 3, 14)  # sample_count < min

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))
        daemon = MyDaemon()
        assert daemon.check_household_unusual_day(frame) is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_before_the_days_typical_last_activity_hour(self, mock_connect):
        """Too early to judge "today" -- the day hasn't finished looking normal or not yet."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (7, 20, 5, 10, 20, 14)

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 14, 0))  # 2pm, before 20:00
        daemon = MyDaemon()
        assert daemon.check_household_unusual_day(frame) is None
        mock_cursor.execute.assert_called_once()  # never reached the "today's activity" query

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_only_device_count_deviates(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            (7, 20, 5, 10, 20, 14),
            (7, 2),  # first-activity hour matches typical; only device count is off
        ]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))
        daemon = MyDaemon()
        assert daemon.check_household_unusual_day(frame) is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_only_first_activity_hour_deviates(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            (7, 20, 5, 10, 20, 14),
            (11, 7),  # device count within typical range; only the hour is off
        ]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))
        daemon = MyDaemon()
        assert daemon.check_household_unusual_day(frame) is None

    def test_returns_none_when_frame_is_missing_local_dt_or_day_mood(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        with patch("services.service_daemon.alfr3ddaemon.pymysql.connect") as mock_connect:
            frame = _make_frame(local_dt=None, day_mood=None)
            assert daemon.check_household_unusual_day(frame) is None
            mock_connect.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 21, 0))
        daemon = MyDaemon()
        card = daemon.check_household_unusual_day(frame)

        assert card is None
        mock_db.close.assert_called_once()


class TestPruneHouseholdEvents:
    """Tests for prune_household_events() (SA-11 Phase 1)."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_deletes_rows_older_than_the_retention_cutoff(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import prune_household_events

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 42

        prune_household_events()

        delete_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "DELETE FROM household_events" in call.args[0]
        ]
        assert len(delete_calls) == 1
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_rolls_back_and_closes_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import prune_household_events

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        prune_household_events()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestPruneAttentionTelemetryHistory:
    """Tests for prune_attention_telemetry_history() (SA-2)."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_deletes_rows_older_than_the_retention_cutoff(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import prune_attention_telemetry_history

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 7

        prune_attention_telemetry_history()

        delete_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "DELETE FROM attention_telemetry_history" in call.args[0]
        ]
        assert len(delete_calls) == 1
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_rolls_back_and_closes_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import prune_attention_telemetry_history

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        prune_attention_telemetry_history()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestAttentionTelemetryTrend:
    """Tests for MyDaemon._attention_telemetry_trend() (SA-2)."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_below_sample_floor(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(10, 2)] * 3

        assert MyDaemon()._attention_telemetry_trend() is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_medians_at_or_above_sample_floor(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon, ATTENTION_TREND_MIN_SAMPLES

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        rows = [(10, 2)] * (ATTENTION_TREND_MIN_SAMPLES - 1) + [(30, 8)]
        mock_cursor.fetchall.return_value = rows

        trend = MyDaemon()._attention_telemetry_trend()

        assert trend["sample_count"] == ATTENTION_TREND_MIN_SAMPLES
        assert trend["median_switch_count"] == 10
        assert trend["median_unlock_count"] == 2

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert MyDaemon()._attention_telemetry_trend() is None


class TestCheckNowPlaying:
    """Tests for MyDaemon.check_now_playing(). frame.playback/frame.persisted_now_playing
    (SA-4) replace what used to be a mocked live Spotify fetch and a mocked DB read --
    _write_now_playing_config()'s own DB write is unchanged, still needs pymysql mocked."""

    def _playback_state(self, track_id="track1", name="Song", artists=None, is_playing=True):
        return {
            "is_playing": is_playing,
            "item": {"id": track_id, "name": name, "artists": artists or ["Artist"]},
        }

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_nothing_playing_returns_none_without_touching_db_or_producer(
        self, mock_connect, mock_producer
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(playback={"is_playing": False, "item": None})
        daemon = MyDaemon()
        result = daemon.check_now_playing(frame)

        assert result is None
        mock_connect.assert_not_called()
        mock_producer.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_new_track_persists_state_and_publishes_event(self, mock_connect, mock_producer):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(playback=self._playback_state(), persisted_now_playing=None)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1  # UPDATE "succeeds" -> no INSERT fallback

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing(frame)

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
        published_event = orjson.loads(mock_p.send.call_args.args[1])
        assert published_event["subject_type"] == "track"
        assert published_event["subject_id"] == "track1"
        assert published_event["verb"] == "play_start"

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_unchanged_track_does_not_rewrite_or_republish(self, mock_connect, mock_producer):
        """Same track_id + is_playing as last cycle must not spam config writes
        or event-stream messages every ~60s poll."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            playback=self._playback_state(track_id="track1", is_playing=True),
            persisted_now_playing={
                "track_id": "track1",
                "title": "Song",
                "artist": "Artist",
                "is_playing": True,
            },
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing(frame)

        assert card is not None
        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 0
        mock_p.send.assert_not_called()

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_pause_transition_persists_state_but_returns_no_card(self, mock_connect, mock_producer):
        """A track paused (item still present, is_playing False) must still
        get persisted to config -- check_cross_surface_continuity() depends
        on that "paused N minutes ago" state -- but produces no situational-
        awareness card and no event-stream announcement of its own."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            playback=self._playback_state(track_id="track1", is_playing=False),
            persisted_now_playing={
                "track_id": "track1",
                "title": "Song",
                "artist": "Artist",
                "is_playing": True,
            },
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = MyDaemon()
        card = daemon.check_now_playing(frame)

        assert card is None
        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 1
        mock_p.send.assert_not_called()

    def test_no_playback_data_is_caught_and_returns_none(self):
        """frame.playback is None whenever build_context_frame()'s own fetch failed (e.g.
        Spotify unreachable) -- must not crash, same graceful-degradation contract as the
        other frame-backed checks."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        result = daemon.check_now_playing(_make_frame(playback=None))

        assert result is None


class TestCheckCrossSurfaceContinuity:
    """Tests for MyDaemon.check_cross_surface_continuity(). frame.persisted_now_playing/
    frame.launcher_context.surface_state (SA-4) replace two of the three DB reads this rule
    used to make -- only the routines-edited query is still its own pymysql.connect() call."""

    @staticmethod
    def _config_dict(minutes_ago, **fields):
        return {
            **fields,
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
        }

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_offers_resume_for_a_recently_paused_track(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # routines: none edited

        frame = _make_frame(
            persisted_now_playing=self._config_dict(
                4, track_id="track1", title="Song", is_playing=False
            ),
            launcher_context=_make_launcher_context(surface_state={}),
        )
        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity(frame)

        assert result["mode"] == "cross_surface_continuity"
        assert result["resume_type"] == "music"
        assert result["resume_target"] == "track1"
        assert "Song" in result["content"]
        assert result["data"]["minutes_ago"] == 4

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_ignores_a_paused_track_older_than_staleness_window(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        frame = _make_frame(
            persisted_now_playing=self._config_dict(
                120, track_id="track1", title="Song", is_playing=False
            ),
            launcher_context=_make_launcher_context(surface_state={}),
        )
        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity(frame)

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
        mock_cursor.fetchone.return_value = None  # routines: none edited

        frame = _make_frame(
            persisted_now_playing=self._config_dict(
                10, track_id="track1", title="Song", is_playing=False
            ),
            launcher_context=_make_launcher_context(
                surface_state=self._config_dict(1, terminal_session_active=True)
            ),
        )
        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity(frame)

        assert result["resume_type"] == "terminal"

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_nothing_available(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        frame = _make_frame(
            persisted_now_playing={}, launcher_context=_make_launcher_context(surface_state={})
        )
        daemon = MyDaemon()
        result = daemon.check_cross_surface_continuity(frame)

        assert result is None


class TestReadFreshAttentionTelemetry:
    """Tests for MyDaemon._read_fresh_attention_telemetry() -- the staleness gate
    build_context_frame() calls once per cycle to populate
    frame.launcher_context.attention_snapshot. check_attention_focus()/
    check_wind_down_signal() only see the already-filtered result (None once stale),
    so this is where the staleness cutoff itself is covered."""

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_the_snapshot_when_fresh(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(5, switch_count=20)

        snapshot = MyDaemon()._read_fresh_attention_telemetry()

        assert snapshot["switch_count"] == 20

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_snapshot_is_stale(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(120, switch_count=20)

        assert MyDaemon()._read_fresh_attention_telemetry() is None

    @patch("services.service_daemon.alfr3ddaemon.pymysql.connect")
    def test_returns_none_when_no_snapshot_reported_yet(self, mock_connect):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        assert MyDaemon()._read_fresh_attention_telemetry() is None


class TestCheckAttentionFocus:
    """Tests for MyDaemon.check_attention_focus(). frame.launcher_context.attention_snapshot/
    .attention_trend (SA-4) replace what used to be mocked DB reads -- both are plain dicts
    the test constructs directly, since _read_fresh_attention_telemetry()'s own staleness
    logic is covered separately (TestReadFreshAttentionTelemetry)."""

    def test_fires_when_switching_is_high_and_not_media_heavy(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 20,
                    "unlock_count": 1,
                    "dwell_by_category_ms": {"terminal": 600000, "media": 100000},
                },
                attention_trend=None,
            )
        )
        result = MyDaemon().check_attention_focus(frame)

        assert result["mode"] == "attention_focus"
        assert result["priority"] == 3.6
        assert result["switch_count"] == 20
        assert result["data"]["because"]

    def test_returns_none_when_switch_count_is_low(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 3,
                    "dwell_by_category_ms": {"terminal": 600000},
                },
                attention_trend=None,
            )
        )
        assert MyDaemon().check_attention_focus(frame) is None

    def test_returns_none_when_switching_is_media_heavy(self):
        """High switch count while mostly dwelling in media is the wind-down
        pattern, not focus -- must not double-fire both cards."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 20,
                    "dwell_by_category_ms": {"media": 800000, "terminal": 100000},
                },
                attention_trend=None,
            )
        )
        assert MyDaemon().check_attention_focus(frame) is None

    def test_returns_none_when_no_snapshot(self):
        """frame.launcher_context.attention_snapshot is None whenever
        _read_fresh_attention_telemetry() found nothing fresh -- stale or never reported,
        same either way from this rule's perspective."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(attention_snapshot=None, attention_trend=None)
        )
        assert MyDaemon().check_attention_focus(frame) is None

    def test_uses_household_trend_once_enough_history_exists(self):
        """Above ATTENTION_TREND_MIN_SAMPLES, the fire threshold becomes this
        household's own median switch_count + grace -- not the fixed
        ATTENTION_FOCUS_MIN_SWITCHES floor. A switch_count that would fire
        under the fixed threshold (15) must not fire once trend says this
        household's median is much higher (20 -> threshold 25)."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 18,
                    "dwell_by_category_ms": {"terminal": 600000},
                },
                attention_trend={"median_switch_count": 20, "median_unlock_count": 3},
            )
        )
        assert MyDaemon().check_attention_focus(frame) is None  # 18 < 20 + 5 grace = 25

    def test_fires_above_household_trend_threshold(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 30,
                    "dwell_by_category_ms": {"terminal": 600000},
                },
                attention_trend={"median_switch_count": 20, "median_unlock_count": 3},
            )
        )
        result = MyDaemon().check_attention_focus(frame)

        assert result["switch_count"] == 30

    def test_falls_back_to_fixed_threshold_when_no_trend(self):
        """No trend yet (below ATTENTION_TREND_MIN_SAMPLES, or a DB error) -- the fixed
        ATTENTION_FOCUS_MIN_SWITCHES threshold governs instead."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "switch_count": 18,
                    "dwell_by_category_ms": {"terminal": 600000},
                },
                attention_trend=None,
            )
        )
        result = MyDaemon().check_attention_focus(frame)

        assert result["switch_count"] == 18  # 18 >= fixed ATTENTION_FOCUS_MIN_SWITCHES (15)


class TestCheckWindDownSignal:
    """Tests for MyDaemon.check_wind_down_signal(). frame.day_mood/frame.launcher_context.
    attention_snapshot/.attention_trend (SA-4) replace what used to be mocked DB reads."""

    def test_fires_when_night_and_high_unlocks_and_media_heavy(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "unlock_count": 8,
                    "switch_count": 2,
                    "dwell_by_category_ms": {"media": 900000, "terminal": 50000},
                },
                attention_trend=None,
            ),
        )
        result = MyDaemon().check_wind_down_signal(frame)

        assert result["mode"] == "wind_down_signal"
        assert result["priority"] == 5.8
        assert result["unlock_count"] == 8
        assert result["data"]["because"]

    def test_returns_none_when_not_night(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "day"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 8, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        assert MyDaemon().check_wind_down_signal(frame) is None

    def test_returns_none_when_unlock_count_is_low(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 1, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        assert MyDaemon().check_wind_down_signal(frame) is None

    def test_returns_none_when_dwell_is_not_media_heavy(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={
                    "unlock_count": 8,
                    "dwell_by_category_ms": {"terminal": 900000, "media": 50000},
                },
                attention_trend=None,
            ),
        )
        assert MyDaemon().check_wind_down_signal(frame) is None

    def test_returns_none_when_no_snapshot(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(attention_snapshot=None, attention_trend=None),
        )
        assert MyDaemon().check_wind_down_signal(frame) is None

    def test_uses_household_trend_once_enough_history_exists(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 6, "dwell_by_category_ms": {"media": 900000}},
                attention_trend={"median_switch_count": 2, "median_unlock_count": 8},
            ),
        )
        result = MyDaemon().check_wind_down_signal(frame)

        assert result is None  # 6 < trend threshold (8 + 2 grace = 10)

    def test_fires_above_household_trend_threshold(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 12, "dwell_by_category_ms": {"media": 900000}},
                attention_trend={"median_switch_count": 2, "median_unlock_count": 8},
            ),
        )
        result = MyDaemon().check_wind_down_signal(frame)

        assert result["unlock_count"] == 12

    def test_falls_back_to_fixed_threshold_when_no_trend(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 6, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        result = MyDaemon().check_wind_down_signal(frame)

        assert result["unlock_count"] == 6  # 6 >= fixed WIND_DOWN_MIN_UNLOCKS (5)


class TestCheckPartyAdvisory:
    """Tests for MyDaemon.check_party_advisory(). frame.local_dt/frame.day_mood/
    frame.playback (SA-4) replace what used to be mocked get_env_local_time()/
    get_playback_state() calls."""

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    @patch("common.spotify_utils.get_track_energy")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.is_party_night")
    def test_fires_for_high_energy_track_on_a_weeknight_night(
        self, mock_is_party_night, mock_get_track_energy, mock_get_producer
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_is_party_night.return_value = False
        mock_get_track_energy.return_value = 0.9
        mock_get_producer.return_value = None

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Loud Song"}},
        )
        result = MyDaemon().check_party_advisory(frame)

        assert result is not None
        assert result["mode"] == "party_advisory"
        assert result["priority"] == 3.2
        assert "Loud Song" in result["content"]
        assert result["data"]["track_name"] == "Loud Song"
        assert result["data"]["energy"] == 0.9
        assert result["data"]["day_of_week"] == "Tuesday"
        assert result["data"]["because"]

    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.is_party_night")
    def test_returns_none_on_a_declared_party_night(self, mock_is_party_night):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_is_party_night.return_value = True

        frame = _make_frame(
            local_dt=datetime(2026, 8, 14, 23, 30),  # Friday
            day_mood={"time_of_day": "night", "day_of_week": "Friday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Loud Song"}},
        )
        assert MyDaemon().check_party_advisory(frame) is None

    def test_returns_none_when_frame_fields_missing(self):
        """frame.local_dt/frame.day_mood are None on a DB error building the frame --
        must not crash."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        assert MyDaemon().check_party_advisory(_make_frame(local_dt=None, day_mood=None)) is None

    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.is_party_night")
    def test_returns_none_when_nothing_playing(self, mock_is_party_night):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_is_party_night.return_value = False

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": False, "item": None},
        )
        assert MyDaemon().check_party_advisory(frame) is None

    @patch("common.spotify_utils.get_track_energy")
    @patch("services.service_daemon.alfr3ddaemon.spotify_utils.is_party_night")
    def test_returns_none_when_energy_below_threshold(
        self, mock_is_party_night, mock_get_track_energy
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_is_party_night.return_value = False
        mock_get_track_energy.return_value = 0.1

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Chill Song"}},
        )
        assert MyDaemon().check_party_advisory(frame) is None


class TestFocusUtils:
    """Tests for focus_utils.looks_like_call()."""

    def test_zoom_url_matches_at_probable_tier(self):
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call("https://us02web.zoom.us/j/123456", None) == PROBABLE

    def test_meet_google_url_matches_at_probable_tier(self):
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "Join here: https://meet.google.com/abc-defg-hij") == PROBABLE

    def test_teams_url_matches_at_probable_tier(self):
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call("https://teams.microsoft.com/l/meetup-join/xyz", None) == PROBABLE

    def test_bare_zoom_mention_matches_at_probable_tier(self):
        """Organizers sometimes paste a friendly label instead of a raw URL."""
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "Quick Zoom to review the roadmap") == PROBABLE

    def test_ordinary_address_and_notes_do_not_match(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call("123 Main St", "Bring snacks") is None

    def test_no_address_or_notes_does_not_match(self):
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call(None, None) is None

    def test_matching_is_case_insensitive(self):
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "ZOOM.US/j/999") == PROBABLE
        assert looks_like_call(None, "Let's do a GOOGLE MEET") == PROBABLE

    def test_conference_uri_present_is_confirmed_regardless_of_text(self):
        """A real synced conference_uri (SA-7) is a confirmed call even when
        address/notes are empty or ordinary."""
        from services.service_daemon.utils.focus_utils import looks_like_call, CONFIRMED

        assert looks_like_call(None, None, "https://meet.google.com/abc-defg-hij") == CONFIRMED
        assert looks_like_call("123 Main St", "Bring snacks", "https://zoom.us/j/1") == CONFIRMED

    def test_documented_false_positive_still_falls_to_probable_not_confirmed(self):
        """The documented false-positive case ("re-zoom the picture") must
        still only reach the probable tier -- text content alone can never
        promote a card to confirmed."""
        from services.service_daemon.utils.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "re-zoom the picture before the meeting", None) == PROBABLE

    def test_no_conference_uri_falls_back_to_text_heuristic(self):
        """An event with no conferencing data at all and ordinary text is
        neither confirmed nor probable."""
        from services.service_daemon.utils.focus_utils import looks_like_call

        assert looks_like_call("123 Main St", "Bring snacks", None) is None


class TestCheckFocusNeeded:
    """Tests for MyDaemon.check_focus_needed()."""

    @staticmethod
    def _make_event(
        minutes_from_now,
        address=None,
        notes=None,
        title="Standup",
        conference_uri=None,
        conference_solution=None,
    ):
        return [
            {
                "title": title,
                "start_time": datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
                "address": address,
                "notes": notes,
                "conference_uri": conference_uri,
                "conference_solution": conference_solution,
            }
        ]

    def test_fires_at_probable_tier_when_call_like_and_within_lead_time(self):
        """frame.upcoming_events (SA-4) replaces this rule's own
        calendar_utils.get_upcoming_events() call -- check_events() reads the same fetch."""
        from services.service_daemon.alfr3ddaemon import MyDaemon
        from services.service_daemon.utils.focus_utils import PROBABLE

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, address="https://zoom.us/j/123", title="1:1 with Bob"
            )
        )
        daemon = MyDaemon()
        card = daemon.check_focus_needed(frame)

        assert card is not None
        assert card["mode"] == "focus_needed"
        assert "1:1 with Bob" in card["content"]
        assert card["priority"] == 3.5
        assert card["confidence"] == PROBABLE
        assert card["conference_uri"] is None
        assert card["data"]["title"] == "1:1 with Bob"
        assert card["data"]["minutes_until"] in (4, 5)  # sub-second timing tolerance

    def test_fires_at_confirmed_tier_when_conference_uri_present(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon
        from services.service_daemon.utils.focus_utils import CONFIRMED

        frame = _make_frame(
            upcoming_events=self._make_event(
                5,
                title="1:1 with Bob",
                conference_uri="https://meet.google.com/abc-defg-hij",
                conference_solution="Google Meet",
            )
        )
        daemon = MyDaemon()
        card = daemon.check_focus_needed(frame)

        assert card is not None
        assert card["confidence"] == CONFIRMED
        assert card["conference_uri"] == "https://meet.google.com/abc-defg-hij"
        assert "Google Meet" in card["content"]
        assert "1:1 with Bob" in card["content"]

    def test_documented_false_positive_fires_but_only_at_probable_tier(self):
        """ "re-zoom the picture" is a known false positive of the text
        heuristic -- it must still fire (accepted limitation of tier 2), but
        never be promoted to confirmed."""
        from services.service_daemon.alfr3ddaemon import MyDaemon
        from services.service_daemon.utils.focus_utils import PROBABLE

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, notes="re-zoom the picture before the meeting", title="Photo review"
            )
        )
        daemon = MyDaemon()
        card = daemon.check_focus_needed(frame)

        assert card is not None
        assert card["confidence"] == PROBABLE

    def test_pre_migration_event_with_null_conference_fields_does_not_error(self):
        """An event synced before this migration (or one predating
        get_upcoming_events() returning the new keys) has conference_uri/
        conference_solution as None -- must behave exactly like today, not
        raise."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, address="https://zoom.us/j/123", title="1:1 with Bob"
            )
        )
        daemon = MyDaemon()
        card = daemon.check_focus_needed(frame)

        assert card is not None

    def test_returns_none_when_outside_lead_time(self):
        """Matches, but starts well beyond FOCUS_LEAD_MINUTES away."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(upcoming_events=self._make_event(45, address="https://zoom.us/j/123"))
        daemon = MyDaemon()
        assert daemon.check_focus_needed(frame) is None

    def test_returns_none_when_event_does_not_look_like_call(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            upcoming_events=self._make_event(5, address="123 Main St", notes="Bring donuts")
        )
        daemon = MyDaemon()
        assert daemon.check_focus_needed(frame) is None

    def test_returns_none_when_no_upcoming_event(self):
        """Mirrors check_events()'s existing "no event" behavior."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_focus_needed(_make_frame(upcoming_events=None)) is None


class TestCheckEvents:
    """Regression tests for check_events(). A backend-computed travel/leave-by
    card (check_travel(), Google Maps Directions) briefly existed as a
    separate card but was removed -- it needed a paid Maps API tier the
    household isn't using. The "Open Maps" destination action now lives
    entirely client-side in alfr3d_deck's next_event_soon rule instead, so
    check_events() here only ever shows the plain title/time line."""

    def test_event_card_shows_plain_title_and_time(self):
        """check_events() returns a well-formed card with no travel numbers and
        none of the old dead placeholder's dress/umbrella wording.

        `frame.upcoming_events` (SA-4) replaces this rule's own
        calendar_utils.get_upcoming_events() call."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        frame = _make_frame(
            now=now,
            upcoming_events=[
                {
                    "title": "Dentist",
                    "start_time": now + timedelta(minutes=30),
                    "address": "123 Main St",
                    "notes": None,
                }
            ],
        )

        daemon = MyDaemon()
        card = daemon.check_events(frame)

        assert card is not None
        assert card["mode"] == "event"
        assert card["priority"] == 2
        assert "Dentist" in card["content"]
        assert card["data"]["title"] == "Dentist"
        assert card["data"]["minutes_until"] == 30
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

    def test_returns_none_when_no_upcoming_event(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_events(_make_frame(upcoming_events=None)) is None

    def test_returns_none_when_event_more_than_three_hours_out(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            upcoming_events=[
                {
                    "title": "Dentist",
                    "start_time": datetime.now(timezone.utc) + timedelta(hours=4),
                    "address": "123 Main St",
                    "notes": None,
                }
            ]
        )

        daemon = MyDaemon()
        assert daemon.check_events(frame) is None


class TestCheckTravel:
    """Tests for MyDaemon.check_travel() (SA-6) -- restores what commit 08509ce removed, on
    self-hosted infrastructure. See todo/todo_self_hosted_routing.md for the Phase 0 spike."""

    def _frame_with_event(
        self, now, minutes_to_start=45, address="100 Queen St W", conference_uri=None
    ):
        return _make_frame(
            now=now,
            upcoming_events=[
                {
                    "title": "Dentist",
                    "start_time": now + timedelta(minutes=minutes_to_start),
                    "address": address,
                    "notes": None,
                    "conference_uri": conference_uri,
                }
            ],
        )

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.get_route")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.fetch_home_coordinates")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_fires_when_leave_by_is_within_the_lead_window(
        self, mock_geocode, mock_home, mock_route
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 20, "distance_km": 12.3}

        # Event in 45 min, 20 min drive -> leave in 25 min, within the 30 min lead window.
        frame = self._frame_with_event(now, minutes_to_start=45)
        daemon = MyDaemon()
        card = daemon.check_travel(frame)

        assert card is not None
        assert card["mode"] == "travel"
        assert card["priority"] == 2.5
        assert "Dentist" in card["content"]
        assert card["data"]["duration_minutes"] == 20
        assert card["data"]["distance_km"] == 12.3
        assert card["data"]["traffic_aware"] is False
        assert card["data"]["because"]

    def test_returns_none_when_no_upcoming_event(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_travel(_make_frame(upcoming_events=None)) is None

    def test_returns_none_when_address_is_blank(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        frame = self._frame_with_event(now, address="")
        daemon = MyDaemon()
        assert daemon.check_travel(frame) is None

    def test_returns_none_for_a_conferencing_event_even_with_an_address(self):
        """A video call has nowhere to drive to -- check_focus_needed()'s job, not this one's."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        frame = self._frame_with_event(now, conference_uri="https://meet.google.com/abc-defg-hij")
        daemon = MyDaemon()
        assert daemon.check_travel(frame) is None

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_returns_none_when_address_cannot_be_geocoded(self, mock_geocode):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_geocode.return_value = None
        now = datetime.now(timezone.utc)
        daemon = MyDaemon()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.fetch_home_coordinates")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_returns_none_when_home_location_not_set(self, mock_geocode, mock_home):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = None
        now = datetime.now(timezone.utc)
        daemon = MyDaemon()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.get_route")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.fetch_home_coordinates")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_returns_none_when_routing_service_unreachable(
        self, mock_geocode, mock_home, mock_route
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = None
        now = datetime.now(timezone.utc)
        daemon = MyDaemon()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.get_route")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.fetch_home_coordinates")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_returns_none_when_leave_by_is_too_far_in_the_future(
        self, mock_geocode, mock_home, mock_route
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 5, "distance_km": 2.0}

        # Event in 3 hours, 5 min drive -> leave in ~175 min, way outside the 30 min lead window.
        frame = self._frame_with_event(now, minutes_to_start=180)
        daemon = MyDaemon()
        assert daemon.check_travel(frame) is None

    @patch("services.service_daemon.alfr3ddaemon.routing_utils.get_route")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.fetch_home_coordinates")
    @patch("services.service_daemon.alfr3ddaemon.routing_utils.geocode_address")
    def test_returns_none_once_leave_by_has_meaningfully_passed(
        self, mock_geocode, mock_home, mock_route
    ):
        """A stale leave-by time is worse than no card -- once the window's passed, stop."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 5, "distance_km": 2.0}

        # Event started 10 min ago, 5 min drive -> should have left 15 min ago, within the
        # (symmetric) 30 min window still -- use a longer overshoot to confirm it clears.
        frame = self._frame_with_event(now, minutes_to_start=-70)
        daemon = MyDaemon()
        assert daemon.check_travel(frame) is None


class TestCheckWeatherAdvisory:
    """Tests for MyDaemon.check_weather_advisory()."""

    def test_fires_when_rain_probability_exceeds_threshold(self):
        """frame.environment (SA-4) replaces this rule's own DB read."""
        from services.service_daemon.alfr3ddaemon import (
            MyDaemon,
            RAIN_ADVISORY_THRESHOLD,
            FORECAST_HOURS_AHEAD,
        )

        frame = _make_frame(environment={"forecast_rain_probability": RAIN_ADVISORY_THRESHOLD + 10})
        daemon = MyDaemon()
        card = daemon.check_weather_advisory(frame)

        assert card is not None
        assert card["mode"] == "weather_advisory"
        assert card["priority"] == 4.5
        assert str(FORECAST_HOURS_AHEAD) in card["content"]
        assert "umbrella" in card["content"]
        assert card["data"]["forecast_rain_probability"] == RAIN_ADVISORY_THRESHOLD + 10
        assert card["data"]["hours_ahead"] == FORECAST_HOURS_AHEAD

    def test_returns_none_below_threshold(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon, RAIN_ADVISORY_THRESHOLD

        frame = _make_frame(environment={"forecast_rain_probability": RAIN_ADVISORY_THRESHOLD - 5})
        daemon = MyDaemon()
        assert daemon.check_weather_advisory(frame) is None

    def test_returns_none_when_forecast_not_yet_populated(self):
        """No forecast snapshot yet (NULL column) must not crash, just skip the card."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(environment={"forecast_rain_probability": None})
        daemon = MyDaemon()
        assert daemon.check_weather_advisory(frame) is None

    def test_returns_none_when_no_environment_row(self):
        """frame.environment is None (no row, or a DB error building the frame) -- must
        not crash, same as check_weather()."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_weather_advisory(_make_frame(environment=None)) is None


class TestCheckTime:
    """Tests for MyDaemon.check_time() -- previously exercised only indirectly
    via decide_displays() stubs, never as its own real (unmocked) call."""

    def test_returns_well_formed_time_card(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        card = daemon.check_time(_make_frame())

        assert card["mode"] == "time"
        assert card["priority"] == 1
        # content is a real ISO-8601 timestamp, not a placeholder string.
        datetime.fromisoformat(card["content"])

    def test_shares_the_frames_timestamp_not_its_own(self):
        """SA-4 acceptance criterion: all cards in one cycle share a single timestamp."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(now=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        daemon = MyDaemon()
        card = daemon.check_time(frame)

        assert card["content"] == "2026-01-01T12:00:00+00:00"


class TestCheckWeather:
    """Tests for MyDaemon.check_weather() -- previously exercised only via
    decide_displays() stubs, never with a real DB-backed call."""

    def test_returns_formatted_weather_card(self):
        """frame.environment (SA-4) replaces this rule's own DB read."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            environment={
                "city": "Testville",
                "description": "clear",
                "low": 10,
                "high": 22,
                "subjective_feel": "pleasant",
                "forecast_rain_probability": None,
            }
        )
        daemon = MyDaemon()
        card = daemon.check_weather(frame)

        assert card == {
            "mode": "weather",
            "content": "Testville: pleasant, clear, 10°C to 22°C",
            "priority": 5,
            "data": {
                "city": "Testville",
                "subjective_feel": "pleasant",
                "description": "clear",
                "low": 10,
                "high": 22,
            },
        }

    def test_returns_none_when_no_environment_row(self):
        """frame.environment is None when the frame build found no row (or a DB error) --
        check_weather() must not crash, same as before."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        daemon = MyDaemon()
        assert daemon.check_weather(_make_frame(environment=None)) is None


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
        card = daemon.check_emails(_make_frame())

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
        assert daemon.check_emails(_make_frame()) is None


class TestContextFrameFetchers:
    """Tests for context_frame.py's standalone fetchers (SA-4) -- both new for this
    refactor, neither existed as a reusable function before."""

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_online_devices_splits_known_and_unknown(self, mock_connect):
        from services.service_daemon.utils.context_frame import fetch_online_devices

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("athos", "Athos's Phone"),
            ("athos", "Athos's Laptop"),
            (None, "Unclaimed Device"),
        ]

        result = fetch_online_devices()

        assert result["known_names"] == ["athos"]
        assert result["known_count"] == 1
        assert result["unknown_count"] == 1

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_online_devices_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.utils.context_frame import fetch_online_devices

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_online_devices() is None

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_smarthome_online_returns_sorted_names(self, mock_connect):
        from services.service_daemon.utils.context_frame import fetch_smarthome_online

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("Living Room Lamp",), ("Garage Heater",)]

        assert fetch_smarthome_online() == ["Garage Heater", "Living Room Lamp"]

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_smarthome_online_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.utils.context_frame import fetch_smarthome_online

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_smarthome_online() is None

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_a_dict(self, mock_connect):
        from services.service_daemon.utils.context_frame import fetch_environment_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Testville", "clear", 10, 22, "pleasant", 40)

        result = fetch_environment_snapshot("test_env")

        assert result == {
            "city": "Testville",
            "description": "clear",
            "low": 10,
            "high": 22,
            "subjective_feel": "pleasant",
            "forecast_rain_probability": 40,
        }

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_none_when_no_row(self, mock_connect):
        from services.service_daemon.utils.context_frame import fetch_environment_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        assert fetch_environment_snapshot("test_env") is None

    @patch("services.service_daemon.utils.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.utils.context_frame import fetch_environment_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_environment_snapshot("test_env") is None


class TestRoutingUtils:
    """Tests for routing_utils.py (SA-6) -- the self-hosted routing/geocoding client
    check_travel() depends on. See todo/todo_self_hosted_routing.md for the Phase 0 spike that
    justified this design."""

    @patch("services.service_daemon.utils.routing_utils._write_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils._read_geocode_cache")
    def test_geocode_address_returns_cached_coordinates_without_calling_nominatim(
        self, mock_read_cache, mock_write_cache
    ):
        from services.service_daemon.utils import routing_utils

        mock_read_cache.return_value = (43.65, -79.38)

        with patch("services.service_daemon.utils.routing_utils.requests.get") as mock_get:
            result = routing_utils.geocode_address("100 Queen St W, Toronto")

        assert result == (43.65, -79.38)
        mock_get.assert_not_called()
        mock_write_cache.assert_not_called()

    @patch("services.service_daemon.utils.routing_utils._write_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils._read_geocode_cache")
    def test_geocode_address_returns_none_for_a_cached_not_found_without_requerying(
        self, mock_read_cache, mock_write_cache
    ):
        """A row exists (address was looked up before) but latitude/longitude are NULL -- a
        cached "not found", distinct from no cache row at all. Must not hit Nominatim again."""
        from services.service_daemon.utils import routing_utils

        mock_read_cache.return_value = (None, None)

        with patch("services.service_daemon.utils.routing_utils.requests.get") as mock_get:
            result = routing_utils.geocode_address("not a real address")

        assert result is None
        mock_get.assert_not_called()
        mock_write_cache.assert_not_called()

    @patch("services.service_daemon.utils.routing_utils._write_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils._read_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils.requests.get")
    def test_geocode_address_calls_nominatim_on_a_cache_miss_and_writes_the_result(
        self, mock_get, mock_read_cache, mock_write_cache
    ):
        from services.service_daemon.utils import routing_utils

        mock_read_cache.return_value = None  # no cache row at all
        mock_get.return_value.json.return_value = [{"lat": "43.65", "lon": "-79.38"}]
        mock_get.return_value.raise_for_status = MagicMock()

        result = routing_utils.geocode_address("100 Queen St W, Toronto")

        assert result == (43.65, -79.38)
        assert mock_get.call_args.kwargs["headers"]["User-Agent"]
        mock_write_cache.assert_called_once_with("100 Queen St W, Toronto", (43.65, -79.38))

    @patch("services.service_daemon.utils.routing_utils._write_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils._read_geocode_cache")
    @patch("services.service_daemon.utils.routing_utils.requests.get")
    def test_geocode_address_caches_a_not_found_result_too(
        self, mock_get, mock_read_cache, mock_write_cache
    ):
        from services.service_daemon.utils import routing_utils

        mock_read_cache.return_value = None
        mock_get.return_value.json.return_value = []  # Nominatim found nothing
        mock_get.return_value.raise_for_status = MagicMock()

        result = routing_utils.geocode_address("nowhere in particular")

        assert result is None
        mock_write_cache.assert_called_once_with("nowhere in particular", None)

    def test_geocode_address_returns_none_for_a_blank_address(self):
        from services.service_daemon.utils import routing_utils

        assert routing_utils.geocode_address("") is None
        assert routing_utils.geocode_address(None) is None
        assert routing_utils.geocode_address("   ") is None

    @patch("services.service_daemon.utils.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_a_tuple(self, mock_connect):
        from services.service_daemon.utils import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (43.65, -79.38)

        assert routing_utils.fetch_home_coordinates("test_env") == (43.65, -79.38)

    @patch("services.service_daemon.utils.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_none_when_location_not_set(self, mock_connect):
        from services.service_daemon.utils import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (None, None)

        assert routing_utils.fetch_home_coordinates("test_env") is None

    @patch("services.service_daemon.utils.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_daemon.utils import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert routing_utils.fetch_home_coordinates("test_env") is None

    @patch("services.service_daemon.utils.routing_utils.requests.get")
    def test_get_route_returns_duration_and_distance(self, mock_get):
        from services.service_daemon.utils import routing_utils

        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "code": "Ok",
            "routes": [{"duration": 1180.1, "distance": 17941.4}],
        }

        result = routing_utils.get_route((43.62, -79.55), (43.65, -79.38))

        assert result["duration_minutes"] == 1180.1 / 60
        assert result["distance_km"] == 17941.4 / 1000

    @patch("services.service_daemon.utils.routing_utils.requests.get")
    def test_get_route_returns_none_when_no_route_found(self, mock_get):
        from services.service_daemon.utils import routing_utils

        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"code": "NoRoute", "routes": []}

        assert routing_utils.get_route((43.62, -79.55), (43.65, -79.38)) is None

    @patch("services.service_daemon.utils.routing_utils.requests.get")
    def test_get_route_returns_none_when_service_unreachable(self, mock_get):
        import requests

        from services.service_daemon.utils import routing_utils

        mock_get.side_effect = requests.exceptions.ConnectionError("routing container down")

        assert routing_utils.get_route((43.62, -79.55), (43.65, -79.38)) is None


class TestBuildContextFrame:
    """Tests for MyDaemon.build_context_frame() (SA-4) -- in particular the acceptance
    criterion that one integration failing (a simulated Spotify outage) must not prevent
    unrelated fields from building."""

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
    @patch("common.spotify_utils.get_playback_state")
    @patch("services.service_daemon.alfr3ddaemon.calendar_utils.get_upcoming_events")
    @patch("services.service_daemon.alfr3ddaemon.context_frame.fetch_environment_snapshot")
    @patch("services.service_daemon.alfr3ddaemon.db_utils.get_env_local_time")
    def test_a_spotify_failure_does_not_prevent_unrelated_fields_from_building(
        self, mock_get_local_time, mock_fetch_environment, mock_get_events, mock_playback
    ):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        mock_get_local_time.return_value = datetime(2026, 8, 11, 19, 0)
        mock_fetch_environment.return_value = {
            "city": "Testville",
            "description": "clear",
            "low": 10,
            "high": 22,
            "subjective_feel": "pleasant",
            "forecast_rain_probability": None,
        }
        mock_get_events.return_value = None
        mock_playback.side_effect = Exception("Spotify unreachable")

        frame = MyDaemon().build_context_frame()

        assert frame.playback is None  # the simulated failure
        assert frame.now is not None
        assert frame.day_mood is not None
        assert frame.environment["city"] == "Testville"

        daemon = MyDaemon()
        assert daemon.check_time(frame) is not None
        assert daemon.check_weather(frame) is not None
        assert daemon.check_events(frame) is None  # no events, but doesn't crash
        assert daemon.check_now_playing(frame) is None  # no playback, but doesn't crash


class TestCheckEmptyHouseStillOn:
    """Tests for MyDaemon.check_empty_house_still_on() (SA-4 Phase 3) -- the rule that
    needs three frame fields at once (online_devices, smarthome_online, day_mood) and
    couldn't have been written before the context frame existed."""

    def test_fires_when_house_empty_smarthome_on_and_evening(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices([(None, "Unclaimed Device")]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        result = MyDaemon().check_empty_house_still_on(frame)

        assert result["mode"] == "empty_house_still_on"
        assert result["priority"] == 2.4
        assert "Living Room Lamp" in result["content"]
        assert result["device_count"] == 1
        assert result["data"]["smarthome_device_names"] == ["Living Room Lamp"]
        assert result["data"]["because"]

    def test_returns_none_when_a_claimed_device_is_online(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices([("athos", "Athos's Phone")]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        assert MyDaemon().check_empty_house_still_on(frame) is None

    def test_returns_none_when_nothing_smarthome_is_on(self):
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices([]),
            smarthome_online=[],
            day_mood={"time_of_day": "evening"},
        )
        assert MyDaemon().check_empty_house_still_on(frame) is None

    def test_returns_none_during_the_day(self):
        """Not noteworthy during the day -- 'everyone's out, something's on' is the
        normal daytime state, not an anomaly."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=_online_devices([]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "day"},
        )
        assert MyDaemon().check_empty_house_still_on(frame) is None

    def test_returns_none_when_online_devices_is_none(self):
        """frame.online_devices is None on a DB error building the frame -- must not
        crash."""
        from services.service_daemon.alfr3ddaemon import MyDaemon

        frame = _make_frame(
            online_devices=None,
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        assert MyDaemon().check_empty_house_still_on(frame) is None


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
