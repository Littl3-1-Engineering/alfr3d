"""Tests for the ALFR3D daemon service utilities (situational awareness moved to service_sa in
LF-1a -- see tests/test_sa_service.py)."""

import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import orjson


def _make_frame(**overrides):
    """Build a context_frame.ContextFrame test double (SA-4) with sensible defaults,
    overridden per test. `now` defaults to real current time since most rules only compare
    it against other supplied values, not an exact wall-clock string."""
    from services.service_sa.sa.context_frame import ContextFrame

    frame = ContextFrame()
    frame.now = datetime.now(timezone.utc)
    for key, value in overrides.items():
        setattr(frame, key, value)
    return frame


def _make_launcher_context(**overrides):
    from services.service_sa.sa.context_frame import LauncherContext

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
    @patch("services.common.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_success(self, mock_connect):
        """Test get_upcoming_events returns events when found."""
        from services.common.calendar_utils import get_upcoming_events

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
    @patch("services.common.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_no_events(self, mock_connect):
        """Test get_upcoming_events returns None when no events found."""
        from services.common.calendar_utils import get_upcoming_events

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
    @patch("services.common.calendar_utils.pymysql.connect")
    def test_get_upcoming_events_db_error(self, mock_connect):
        """Test get_upcoming_events handles DB errors gracefully."""
        from services.common.calendar_utils import get_upcoming_events

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
    def test_publishes_created_event_for_a_genuinely_new_calendar_event(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        from services.common.calendar_utils import sync_calendar

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
    def test_persists_conference_metadata_when_present(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """SA-7: an event with structured Google conferencing data gets its
        conference_uri/conference_solution persisted alongside the rest."""
        from services.common.calendar_utils import sync_calendar

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
    def test_persists_null_conference_metadata_when_absent(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """An event with no conferencing data at all persists NULLs, not an
        error -- the common case today."""
        from services.common.calendar_utils import sync_calendar

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
    def test_skips_publish_for_an_unchanged_calendar_event(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        """The same event re-synced unchanged must not be reported as
        'created' -- that would spam an event for every event on every
        sync tick."""
        from services.common.calendar_utils import sync_calendar

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
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
        from services.common.calendar_utils import sync_calendar

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

    @patch("services.common.calendar_utils.get_producer")
    @patch("services.common.calendar_utils.pymysql.connect")
    @patch("services.common.calendar_utils.build")
    @patch("services.common.calendar_utils.get_credentials")
    def test_publishes_removed_event_for_one_dropped_from_the_calendar(
        self, mock_creds, mock_build, mock_connect, mock_get_producer
    ):
        from services.common.calendar_utils import sync_calendar

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
class TestSyncCalendarRoutine:
    # alfr3ddaemon reads KAFKA_BOOTSTRAP_SERVERS at import. These tests used to pass only when an
    # earlier test had already imported it with the variable set; run alone they failed.
    """Tests for alfr3ddaemon.sync_calendar_routine() -- the scheduled job that keeps
    calendar_events fresh between daemon restarts so check_travel() (SA-6) can fire on a
    newly-created event. See todo/sa/todo_leave_by_demo.md."""

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    def test_publishes_calendar_sync_message_to_integrations_topic(self, mock_get_producer):
        from services.service_daemon.alfr3ddaemon import sync_calendar_routine

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        sync_calendar_routine()

        mock_producer.send.assert_called_once()
        topic, payload = mock_producer.send.call_args.args
        assert topic == "integrations"
        assert orjson.loads(payload) == {"type": "calendar", "action": "sync"}

    @patch("services.service_daemon.alfr3ddaemon.get_producer")
    def test_no_producer_is_a_noop(self, mock_get_producer):
        from services.service_daemon.alfr3ddaemon import sync_calendar_routine

        mock_get_producer.return_value = None

        sync_calendar_routine()  # must not raise


class TestExtractConferenceInfo:
    """Tests for calendar_utils._extract_conference_info() (SA-7)."""

    def test_returns_uri_and_solution_from_conference_data(self):
        from services.common.calendar_utils import _extract_conference_info

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
        from services.common.calendar_utils import _extract_conference_info

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
        from services.common.calendar_utils import _extract_conference_info

        assert _extract_conference_info(event) == (
            "https://meet.google.com/legacy-link",
            "Google Meet",
        )

    def test_returns_none_none_when_neither_field_present(self):
        from services.common.calendar_utils import _extract_conference_info

        assert _extract_conference_info({}) == (None, None)

    def test_returns_none_none_when_conference_data_has_no_entry_points(self):
        from services.common.calendar_utils import _extract_conference_info

        event = {"conferenceData": {"conferenceSolution": {"name": "Zoom"}, "entryPoints": []}}
        assert _extract_conference_info(event) == (None, None)


class TestGmailUtils:
    """Tests for gmail_utils.py"""

    def test_check_unread_emails(self):
        """check_unread_emails is a real Gmail API implementation; it returns
        None here only because no OAuth credentials are configured in the test
        environment, not because it's a stub."""
        from services.common.gmail_utils import check_unread_emails

        result = check_unread_emails()

        assert result is None


class TestSpotifyUtils:
    """Tests for spotify_utils.py"""

    def test_resolve_playlist_none_when_not_authorized(self):
        """Test resolve_playlist returns None gracefully when Spotify isn't connected."""
        from unittest.mock import patch
        from services.common.spotify_utils import resolve_playlist

        with patch(
            "common.spotify_utils.find_playlist_for_hint",
            return_value=(None, "Spotify not connected"),
        ):
            result = resolve_playlist("chill vibes")

        assert result is None

    def test_recommend_single_person_morning(self):
        """Test recommend for single person in morning."""
        from services.common.spotify_utils import recommend

        result = recommend(1, 0, "morning")

        assert result["energy"] == 0.15  # 0.2 - 0.05
        assert result["mood"] == "relaxed acoustic"
        assert "acoustic" in result["genre"]

    def test_recommend_family_evening(self):
        """Test recommend for family in evening."""
        from services.common.spotify_utils import recommend

        result = recommend(4, 0, "evening")

        assert result["energy"] == 0.75  # 0.7 + 0.05
        assert result["mood"] == "upbeat alt-rock"
        assert "alt-rock" in result["genre"]

    def test_recommend_party_night_with_guests(self):
        """Test recommend for party with guests at night, on a declared party night."""
        from services.common.spotify_utils import recommend

        result = recommend(8, 3, "night", is_party_night=True)

        assert result["energy"] == 1.0  # 0.9 + 0.08 + 0.05 = 1.03, clamped to 1.0
        assert result["mood"] == "energetic dance"
        assert "dance" in result["genre"]

    def test_recommend_weeknight_caps_energy_despite_big_gathering(self):
        """Same headcount/guests/time as the party-night test above, but without
        is_party_night -- energy must be capped below the party tier, not just
        happen to land lower."""
        from services.common.spotify_utils import recommend

        result = recommend(8, 3, "night")

        assert result["energy"] == 0.79
        assert result["mood"] != "energetic dance"
        assert "dance" not in result["genre"]

    def test_recommend_weeknight_cap_does_not_affect_already_low_energy(self):
        """The weeknight cap (0.79) must not raise energy that was already lower."""
        from services.common.spotify_utils import recommend

        result = recommend(1, 0, "morning")

        assert result["energy"] == 0.15

    def test_recommend_with_weather_rain(self):
        """Test recommend adjusts for rainy weather."""
        from services.common.spotify_utils import recommend

        weather = {"subjective_feel": "rainy", "description": "light rain", "temp": 15}
        result = recommend(3, 0, "day", weather)

        assert result["energy"] == 0.28  # 0.4 - 0.12
        assert "chill" in result["playlist_hint"]

    def test_recommend_with_weather_sunny(self):
        """Test recommend adjusts for sunny weather."""
        from services.common.spotify_utils import recommend

        weather = {"subjective_feel": "sunny", "description": "clear sky", "temp": 25}
        result = recommend(3, 0, "day", weather)

        assert result["energy"] == 0.46  # 0.4 + 0.06
        assert "mellow" in result["playlist_hint"]

    def test_recommend_time_as_int(self):
        """Test recommend handles time_of_day as int."""
        from services.common.spotify_utils import recommend

        result = recommend(2, 0, 14)  # 2 PM = day

        assert result["mood"] == "warm indie"

    def test_recommend_none_time(self):
        """Test recommend defaults to 'day' when time_of_day is None."""
        from services.common.spotify_utils import recommend

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
    @patch("common.day_context.get_day_context")
    @patch("common.db_utils.get_db_connection")
    def test_check_mute_during_day_with_users(self, mock_connect, mock_day_ctx):
        """check_mute returns False inside waking hours with users online."""
        from services.service_daemon.utils.util_routines import check_mute

        mock_day_ctx.return_value = SimpleNamespace(is_waking_hours=True)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(1, "user1")]  # online users

        result = check_mute()

        assert result is False  # waking hours + a listener -> speak

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
    @patch("common.day_context.get_day_context")
    @patch("common.db_utils.get_db_connection")
    def test_check_mute_at_night_no_users(self, mock_connect, mock_day_ctx):
        """check_mute returns True outside waking hours (short-circuits before the
        listeners query)."""
        from services.service_daemon.utils.util_routines import check_mute

        mock_day_ctx.return_value = SimpleNamespace(is_waking_hours=False)

        result = check_mute()

        assert result is True  # asleep -> muted regardless of who's online

    @patch("common.day_context.get_day_context")
    @patch("common.db_utils.get_db_connection")
    def test_check_mute_waking_hours_but_no_listeners(self, mock_connect, mock_day_ctx):
        """Inside waking hours but nobody worth speaking to is online -> muted."""
        from services.service_daemon.utils.util_routines import check_mute

        mock_day_ctx.return_value = SimpleNamespace(is_waking_hours=True)
        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []  # no users online

        assert check_mute() is True


class TestCheckMuteDeckRelay:
    """check_mute bypasses the empty-house gate (only) when a Deck has reported
    recently with its PHONE SPEECH relay on; quiet hours stay authoritative."""

    @staticmethod
    def _blob(relay=True, age_minutes=1):
        observed = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        facets = {"power": {"is_charging": True}}
        if relay is not None:
            facets["speech"] = {"relay_enabled": relay}
        return orjson.dumps(
            {"devices": {"dev-1": {"facets": facets, "observed_at": observed.isoformat()}}}
        ).decode()

    @staticmethod
    def _run(blob, is_sleeping, is_empty):
        from common import db_utils

        cursor = MagicMock()
        cursor.fetchone.return_value = (blob,) if blob is not None else None
        db = MagicMock()
        db.cursor.return_value = cursor
        with (
            patch.object(db_utils, "get_db_connection", return_value=db),
            patch.object(db_utils, "get_mute_state", return_value=(is_sleeping, is_empty)),
        ):
            return db_utils.check_mute_optimized("test_env")

    def test_empty_house_not_muted_when_deck_relay_on(self):
        assert self._run(self._blob(), False, True) is False

    def test_empty_house_muted_when_relay_off(self):
        assert self._run(self._blob(relay=False), False, True) is True

    def test_empty_house_muted_when_relay_unreported(self):
        assert self._run(self._blob(relay=None), False, True) is True

    def test_empty_house_muted_when_report_is_stale(self):
        assert self._run(self._blob(age_minutes=60), False, True) is True

    def test_empty_house_muted_when_nothing_ever_reported(self):
        assert self._run(None, False, True) is True

    def test_quiet_hours_stay_muted_even_with_relay_on(self):
        assert self._run(self._blob(), True, True) is True

    def test_occupied_house_unchanged(self):
        assert self._run(self._blob(), False, False) is False


class TestRecordWeatherRoutine:
    """The hourly silent weather sample (LF-0b follow-up): a `record weather` message, not the
    `check weather` one that makes the environment service announce the weather."""

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
    def test_publishes_record_weather_not_check_weather(self):
        from services.service_daemon import alfr3ddaemon

        producer = MagicMock()
        with patch.object(alfr3ddaemon, "get_producer", return_value=producer):
            alfr3ddaemon.record_weather_routine()

        producer.send.assert_called_once_with("environment", b"record weather")

    @patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "localhost:9092"})
    def test_is_scheduled_hourly_alongside_the_four_hourly_announcement(self):
        import inspect

        from services.service_daemon import alfr3ddaemon

        source = inspect.getsource(alfr3ddaemon.init_daemon)

        assert "schedule.every(1).hours.do(record_weather_routine)" in source
        assert "schedule.every(4).hours.do(check_weather_routine)" in source
