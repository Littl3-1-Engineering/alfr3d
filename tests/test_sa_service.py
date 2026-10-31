"""Tests for service_sa: the situational-awareness engine (rules, context frame, suppression,
baselines), lifted out of service_daemon in LF-1a."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import orjson
import pytest


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


class TestDecideDisplays:
    """Tests for SAEngine.decide_displays() and its DISPLAY_RULES registry."""

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
        from services.service_sa.sa.context_frame import ContextFrame

        with patch(
            "services.service_sa.sa.engine.SAEngine.build_context_frame"
        ) as mock_build, patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_build.return_value = ContextFrame()
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            yield

    SYSTEM_HEALTH_CARD = {
        "mode": "system_health",
        "content": "sh",
        "priority": 2.2,
        "urgent": True,
    }
    DISK_HEALTH_CARD = {"mode": "disk_health", "content": "dh", "priority": 5.9}
    TIME_CARD = {"mode": "time", "content": "t", "priority": 1}
    EVENT_CARD = {"mode": "event", "content": "e", "priority": 2}
    MUSIC_CARD = {"mode": "music", "content": "m", "priority": 3}
    NOW_PLAYING_CARD = {"mode": "music", "content": "np", "priority": 3.1}
    GUEST_OVERSTAY_ADVISORY_CARD = {
        "mode": "guest_overstay_advisory",
        "content": "goa",
        "priority": 3.15,
    }
    PARTY_ADVISORY_CARD = {"mode": "party_advisory", "content": "pa", "priority": 3.2}
    FOCUS_CARD = {"mode": "focus_needed", "content": "f", "priority": 3.5}
    EMAIL_CARD = {"mode": "email", "content": "em", "priority": 4}
    WEATHER_ADVISORY_CARD = {
        "mode": "weather_advisory",
        "content": "wa",
        "priority": 4.5,
    }
    WEATHER_CARD = {"mode": "weather", "content": "w", "priority": 5}
    CLIMATE_ADVISORY_CARD = {
        "mode": "climate_advisory",
        "content": "ca",
        "priority": 5.3,
    }
    CLIMATE_DEVIATION_CARD = {
        "mode": "climate_deviation",
        "content": "cd",
        "priority": 5.4,
    }
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
    PRESENCE_DEVIATION_CARD = {
        "mode": "presence_deviation",
        "content": "athos is out — usually home Fridays around 11:00",
        "priority": 2.75,
        "entity_name": "athos",
        "data": {
            "expected_p_home": 0.9,
            "away_minutes": 180,
            "surprise_bits": 3.3,
            "confidence": 0.39,
            "because": ["..."],
        },
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
        check_guest_overstay_advisory=None,
        check_party_advisory=None,
        check_focus_needed=None,
        check_emails=None,
        check_weather_advisory=None,
        check_weather=None,
        check_climate_advisory=None,
        check_climate_deviation=None,
        check_mood=None,
        check_household_composition=None,
        check_rhythm_break_anomaly=None,
        check_cross_surface_continuity=None,
        check_attention_focus=None,
        check_wind_down_signal=None,
        check_empty_house_still_on=None,
        check_departure_anomaly=None,
        check_presence_deviation=None,
        check_household_unusual_day=None,
        check_system_health=None,
        check_disk_health=None,
    ):
        """Build a SAEngine with each check_* replaced by a stub returning the given card."""
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        daemon.check_time = MagicMock(return_value=check_time)
        daemon.check_events = MagicMock(return_value=check_events)
        daemon.check_travel = MagicMock(return_value=check_travel)
        daemon.check_gatherings = MagicMock(return_value=check_gatherings)
        daemon.check_now_playing = MagicMock(return_value=check_now_playing)
        daemon.check_guest_overstay_advisory = MagicMock(return_value=check_guest_overstay_advisory)
        daemon.check_party_advisory = MagicMock(return_value=check_party_advisory)
        daemon.check_focus_needed = MagicMock(return_value=check_focus_needed)
        daemon.check_emails = MagicMock(return_value=check_emails)
        daemon.check_weather_advisory = MagicMock(return_value=check_weather_advisory)
        daemon.check_weather = MagicMock(return_value=check_weather)
        daemon.check_climate_advisory = MagicMock(return_value=check_climate_advisory)
        daemon.check_climate_deviation = MagicMock(return_value=check_climate_deviation)
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
        daemon.check_presence_deviation = MagicMock(return_value=check_presence_deviation)
        daemon.check_household_unusual_day = MagicMock(return_value=check_household_unusual_day)
        daemon.check_system_health = MagicMock(return_value=check_system_health)
        daemon.check_disk_health = MagicMock(return_value=check_disk_health)
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
        from services.service_sa.sa.engine import SAEngine

        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=self.EVENT_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_now_playing=self.NOW_PLAYING_CARD,
            check_guest_overstay_advisory=self.GUEST_OVERSTAY_ADVISORY_CARD,
            check_party_advisory=self.PARTY_ADVISORY_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
            check_weather_advisory=self.WEATHER_ADVISORY_CARD,
            check_weather=self.WEATHER_CARD,
            check_climate_advisory=self.CLIMATE_ADVISORY_CARD,
            check_climate_deviation=self.CLIMATE_DEVIATION_CARD,
            check_mood=self.MOOD_CARD,
            check_household_composition=self.HOUSEHOLD_COMPOSITION_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
            check_cross_surface_continuity=self.CROSS_SURFACE_CONTINUITY_CARD,
            check_attention_focus=self.ATTENTION_FOCUS_CARD,
            check_wind_down_signal=self.WIND_DOWN_SIGNAL_CARD,
            check_empty_house_still_on=self.EMPTY_HOUSE_STILL_ON_CARD,
            check_departure_anomaly=self.DEPARTURE_ANOMALY_CARD,
            check_presence_deviation=self.PRESENCE_DEVIATION_CARD,
            check_travel=self.TRAVEL_CARD,
            check_household_unusual_day=self.HOUSEHOLD_UNUSUAL_DAY_CARD,
            check_system_health=self.SYSTEM_HEALTH_CARD,
            check_disk_health=self.DISK_HEALTH_CARD,
        )

        result = daemon.decide_displays()

        assert len(result) == len(SAEngine.DISPLAY_RULES)
        assert self.WEATHER_ADVISORY_CARD in result
        assert self.WEATHER_CARD in result
        assert self.CLIMATE_ADVISORY_CARD in result
        assert self.CLIMATE_DEVIATION_CARD in result
        assert self.MOOD_CARD in result
        assert self.FOCUS_CARD in result
        assert self.NOW_PLAYING_CARD in result
        assert self.GUEST_OVERSTAY_ADVISORY_CARD in result
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
        from services.service_sa.sa.engine import SAEngine

        priorities = [priority for _rule_id, priority, _check_name in SAEngine.DISPLAY_RULES]

        assert len(priorities) == len(set(priorities))

    def test_all_categories_firing_simultaneously_is_sorted_capped_and_collision_free(
        self,
    ):
        """End-to-end test of decide_displays() with the full, current category set
        (all DISPLAY_RULES entries) firing at once.

        This is the test to extend when a future PR registers another category:
        add its card to the `self._stub_daemon(...)` call below and to the
        expected `modes` list in priority order.
        """
        daemon = self._stub_daemon(
            check_time=self.TIME_CARD,
            check_events=self.EVENT_CARD,
            check_gatherings=self.MUSIC_CARD,
            check_now_playing=self.NOW_PLAYING_CARD,
            check_guest_overstay_advisory=self.GUEST_OVERSTAY_ADVISORY_CARD,
            check_party_advisory=self.PARTY_ADVISORY_CARD,
            check_focus_needed=self.FOCUS_CARD,
            check_emails=self.EMAIL_CARD,
            check_weather_advisory=self.WEATHER_ADVISORY_CARD,
            check_weather=self.WEATHER_CARD,
            check_climate_advisory=self.CLIMATE_ADVISORY_CARD,
            check_climate_deviation=self.CLIMATE_DEVIATION_CARD,
            check_mood=self.MOOD_CARD,
            check_household_composition=self.HOUSEHOLD_COMPOSITION_CARD,
            check_rhythm_break_anomaly=self.RHYTHM_BREAK_ANOMALY_CARD,
            check_cross_surface_continuity=self.CROSS_SURFACE_CONTINUITY_CARD,
            check_attention_focus=self.ATTENTION_FOCUS_CARD,
            check_wind_down_signal=self.WIND_DOWN_SIGNAL_CARD,
            check_empty_house_still_on=self.EMPTY_HOUSE_STILL_ON_CARD,
            check_departure_anomaly=self.DEPARTURE_ANOMALY_CARD,
            check_presence_deviation=self.PRESENCE_DEVIATION_CARD,
            check_travel=self.TRAVEL_CARD,
            check_household_unusual_day=self.HOUSEHOLD_UNUSUAL_DAY_CARD,
            check_system_health=self.SYSTEM_HEALTH_CARD,
            check_disk_health=self.DISK_HEALTH_CARD,
        )

        result = daemon.decide_displays()

        # Sorted ascending by priority.
        priorities = [card["priority"] for card in result]
        assert priorities == sorted(priorities)

        # Cap behavior: MAX_DISPLAYS == len(DISPLAY_RULES), and every registered
        # rule fired exactly once, so all twenty-four cards come back -- nothing dropped.
        from services.service_sa.sa.engine import SAEngine

        assert len(result) == 25 == SAEngine.MAX_DISPLAYS == len(SAEngine.DISPLAY_RULES)

        # No two cards silently collide on priority value.
        # (music and now_playing intentionally share mode "music" at different
        # priorities -- 3 vs 3.1 -- so they don't collide on priority either.)
        assert len(priorities) == len(set(priorities))

        assert [card["mode"] for card in result] == [
            "time",
            "event",
            "system_health",
            "empty_house_still_on",
            "travel",
            "rhythm_break_anomaly",
            "departure_anomaly",
            "presence_deviation",
            "music",
            "music",
            "guest_overstay_advisory",
            "party_advisory",
            "focus_needed",
            "attention_focus",
            "email",
            "weather_advisory",
            "weather",
            "climate_advisory",
            "climate_deviation",
            "cross_surface_continuity",
            "wind_down_signal",
            "disk_health",
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
    """Tests for SAEngine._card_subject_key()/_card_suppression_reason() and
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
        from services.service_sa.sa.engine import SAEngine

        assert SAEngine._card_subject_key("weather", self.WEATHER_CARD) == ""

    def test_subject_key_uses_entity_name_for_rhythm_break_anomaly(self):
        from services.service_sa.sa.engine import SAEngine

        assert (
            SAEngine._card_subject_key("rhythm_break_anomaly", self.RHYTHM_BREAK_ANOMALY_CARD)
            == "Garage light"
        )

    def test_subject_key_uses_entity_name_for_departure_anomaly(self):
        """SA-3's departure_anomaly is rhythm_break_anomaly's human analogue -- dismissing
        one resident's card must not suppress a different resident's."""
        from services.service_sa.sa.engine import SAEngine

        assert (
            SAEngine._card_subject_key("departure_anomaly", self.DEPARTURE_ANOMALY_CARD) == "Munja"
        )

    def test_subject_key_combines_resume_type_and_target_for_cross_surface_continuity(self):
        from services.service_sa.sa.engine import SAEngine

        assert (
            SAEngine._card_subject_key(
                "cross_surface_continuity", self.CROSS_SURFACE_CONTINUITY_CARD
            )
            == "music:track1"
        )

    def test_suppression_reason_is_none_with_no_history(self):
        from services.service_sa.sa.engine import SAEngine

        assert SAEngine()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_cooldown_right_after_a_dismissal(self):
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))
            ]

            assert SAEngine()._card_suppression_reason("weather", "") == "cooldown"

    def test_suppression_reason_is_none_once_cooldown_has_elapsed(self):
        from services.service_sa.sa.engine import (
            SAEngine,
            CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES,
        )

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            old = datetime.now(timezone.utc) - timedelta(
                minutes=CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES + 5
            )
            mock_cursor.fetchall.return_value = [("dismissed", old.replace(tzinfo=None))]

            assert SAEngine()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_repetition_after_enough_unacknowledged_shows(self):
        from services.service_sa.sa.engine import (
            SAEngine,
            CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES,
        )

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mock_cursor.fetchall.return_value = [
                ("shown", now)
            ] * CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES

            assert SAEngine()._card_suppression_reason("weather", "") == "repetition"

    def test_suppression_reason_is_none_below_repetition_threshold(self):
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mock_cursor.fetchall.return_value = [("shown", now)] * 3

            assert SAEngine()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_a_tap_resets_the_repetition_run(self):
        """A 'tapped' interaction mixed into recent history breaks the
        consecutive-shown run -- only the unbroken run since the most recent
        non-'shown' action counts, even though the total 'shown' count across
        all returned rows exceeds the threshold."""
        from services.service_sa.sa.engine import (
            SAEngine,
            CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES,
        )

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            rows = (
                [("shown", now)] * 3
                + [("tapped", now)]
                + [("shown", now)] * CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES
            )
            mock_cursor.fetchall.return_value = rows

            assert SAEngine()._card_suppression_reason("weather", "") is None

    def test_suppression_reason_is_none_on_db_error(self):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

            assert SAEngine()._card_suppression_reason("weather", "") is None

    def test_dismissed_card_does_not_reappear_next_cycle(self):
        """decide_displays()-level integration: a card whose identity was just
        dismissed is dropped entirely, not just flagged."""
        daemon = self._stub_daemon(check_weather=self.WEATHER_CARD)

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
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

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
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

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
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
        from services.service_sa.sa.engine import SAEngine

        def fetchall_by_subject_key(*args, **_kwargs):
            _rule_id, subject_key, _limit = args
            if subject_key == "Garage light":
                return [("dismissed", datetime.now(timezone.utc).replace(tzinfo=None))]
            return []  # "Kitchen light" has no history at all

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_connect.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.side_effect = lambda: fetchall_by_subject_key(
                *mock_cursor.execute.call_args.args[1]
            )

            daemon = SAEngine()
            assert daemon._card_suppression_reason("rhythm_break_anomaly", "Garage light") == (
                "cooldown"
            )
            assert daemon._card_suppression_reason("rhythm_break_anomaly", "Kitchen light") is None


class TestMoodUtils:
    """Tests for mood_utils.get_day_mood()."""

    def test_time_of_day_boundary_hours(self):
        """Each morning/day/evening/night boundary lands in the correct bucket."""
        from services.service_sa.sa.mood_utils import get_day_mood

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
        from services.service_sa.sa.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 11, 19, 0))  # Tuesday

        assert result["day_of_week"] == "Tuesday"
        assert result["is_weekend"] is False
        assert result["base_energy"] == 0.55

    def test_saturday_evening_gets_weekend_bonus(self):
        """A Saturday evening is bumped above the plain evening baseline."""
        from services.service_sa.sa.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 15, 19, 0))  # Saturday

        assert result["day_of_week"] == "Saturday"
        assert result["is_weekend"] is True
        assert result["base_energy"] == 0.70  # 0.55 evening baseline + 0.15 bonus

    def test_friday_evening_gets_wind_up_bonus_despite_not_being_weekend(self):
        """Friday evening/night gets the same bonus as the weekend, but is_weekend is False."""
        from services.service_sa.sa.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 14, 20, 0))  # Friday

        assert result["day_of_week"] == "Friday"
        assert result["is_weekend"] is False
        assert result["base_energy"] == 0.70  # 0.55 evening baseline + 0.15 bonus

    def test_friday_daytime_has_no_bonus(self):
        """Friday during the day (not evening/night) doesn't get the wind-up bonus."""
        from services.service_sa.sa.mood_utils import get_day_mood

        result = get_day_mood(datetime(2026, 8, 14, 14, 0))  # Friday afternoon

        assert result["base_energy"] == 0.50  # plain day baseline, no bonus

    def test_defaults_to_now_when_omitted(self):
        """Calling with no argument doesn't crash and returns a well-formed dict."""
        from services.service_sa.sa.mood_utils import get_day_mood

        result = get_day_mood()

        assert result["time_of_day"] in ("morning", "day", "evening", "night")
        assert isinstance(result["is_weekend"], bool)
        assert 0.0 <= result["base_energy"] <= 1.0


def _frame_with_day_mood(local_dt):
    """frame.day_mood (SA-4) built from the real mood_utils.get_day_mood(), so tests still
    exercise the real bucket logic rather than hand-crafting the dict."""
    from services.service_sa.sa.mood_utils import get_day_mood

    return _make_frame(local_dt=local_dt, day_mood=get_day_mood(local_dt))


class TestCheckMood:
    """Tests for SAEngine.check_mood(). frame.day_mood (SA-4) replaces this rule's own
    get_env_local_time()/get_day_mood() calls."""

    def test_returns_well_formed_mood_card(self):
        """check_mood() returns a well-formed card with a non-empty content string."""
        from services.service_sa.sa.engine import SAEngine

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 19, 0))  # Tuesday evening
        daemon = SAEngine()
        card = daemon.check_mood(frame)

        assert card["mode"] == "mood"
        assert isinstance(card["content"], str) and card["content"]
        assert card["priority"] == 6
        assert card["data"]["day_of_week"] == "Tuesday"
        assert card["data"]["time_of_day"] == "evening"
        assert isinstance(card["data"]["energy"], float)
        # Priority must not collide with any other registered rule.
        other_priorities = {
            priority for rule_id, priority, _ in SAEngine.DISPLAY_RULES if rule_id != "mood"
        }
        assert card["priority"] not in other_priorities

    def test_low_energy_label_at_night(self):
        """Night baseline energy (0.30) must land in the 'low energy' bucket."""
        from services.service_sa.sa.engine import SAEngine

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 2, 0))  # Tuesday 2am
        daemon = SAEngine()
        card = daemon.check_mood(frame)

        assert "low energy" in card["content"]

    def test_high_energy_label_on_saturday_evening(self):
        """Weekend-bonus energy (0.70) must land in the 'high energy' bucket."""
        from services.service_sa.sa.engine import SAEngine

        frame = _frame_with_day_mood(datetime(2026, 8, 15, 19, 0))  # Saturday evening
        daemon = SAEngine()
        card = daemon.check_mood(frame)

        assert "high energy" in card["content"]

    def test_returns_none_when_day_mood_is_none(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.spotify_utils.resolve_playlist")
    @patch("services.service_sa.sa.engine.spotify_utils.recommend")
    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
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
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_and_rolls_back_on_db_error(self, mock_connect):
        """A pymysql.Error while querying gathering state must not crash
        decide_displays() -- the card is just skipped, same as the other
        DB-backed checks."""
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.spotify_utils.resolve_playlist")
    @patch("services.service_sa.sa.engine.spotify_utils.recommend")
    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
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
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.spotify_utils.resolve_playlist")
    @patch("services.service_sa.sa.engine.spotify_utils.recommend")
    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
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

        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.spotify_utils.resolve_playlist")
    @patch("services.service_sa.sa.engine.spotify_utils.recommend")
    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_publishes_event_stream_message_when_producer_available(
        self,
        mock_connect,
        mock_get_producer,
        mock_recommend,
        mock_resolve,
    ):
        """A gathering-detected event is published to the event-stream topic
        when a Kafka producer is available."""
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.spotify_utils.resolve_playlist")
    @patch("services.service_sa.sa.engine.spotify_utils.recommend")
    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_playlist_resolution_exception_falls_back_to_text_hint(
        self,
        mock_connect,
        mock_producer,
        mock_recommend,
        mock_resolve,
    ):
        """resolve_playlist() raising must not crash check_gatherings() --
        it falls back to the plain text hint, with no playlist_* fields."""
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_no_guests_online(self, mock_connect):
        """No guests online (only residents, or nobody) -- no gathering card,
        and no Spotify recommendation call is made."""
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (0, 3)  # guest_count=0, total_count=3

        daemon = SAEngine()
        result = daemon.check_gatherings(_make_frame())

        assert result is None


class TestCheckHouseholdComposition:
    """Tests for SAEngine.check_household_composition(). frame.online_devices (SA-4)
    replaces this rule's own device/state/user query -- check_empty_house_still_on() reads
    the same fetch."""

    def test_all_online_devices_claimed_is_ambient_priority(self):
        """Every online device belongs to a known household member -- low-urgency
        ambient card, same priority tier as mood."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices(
                [("athos", "Athos's Phone"), ("athos", "Athos's Laptop")]
            )
        )
        result = SAEngine().check_household_composition(frame)

        assert result["mode"] == "household_composition"
        assert result["priority"] == 6.2
        assert result["urgent"] is False
        assert result["known_count"] == 1
        assert result["unknown_count"] == 0
        assert result["data"]["known_names"] == ["athos"]

    def test_unclaimed_device_online_is_elevated_priority(self):
        """An unclaimed/unknown MAC on the network -- elevated, security-relevant
        priority regardless of how many known members are also home."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices([("athos", "Athos's Phone"), (None, "Unclaimed Device")])
        )
        result = SAEngine().check_household_composition(frame)

        assert result["priority"] == 2.3
        assert result["urgent"] is True
        assert result["known_count"] == 1
        assert result["unknown_count"] == 1

    def test_returns_none_when_no_devices_online(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(online_devices=_online_devices([]))
        result = SAEngine().check_household_composition(frame)

        assert result is None

    def test_returns_none_when_frame_field_is_none(self):
        """frame.online_devices is None on a DB error building the frame -- must not crash."""
        from services.service_sa.sa.engine import SAEngine

        result = SAEngine().check_household_composition(_make_frame(online_devices=None))

        assert result is None


class TestCheckRhythmBreakAnomaly:
    """Tests for SAEngine.check_rhythm_break_anomaly() -- not a frame field (SA-4), this
    device/entity_baselines join isn't duplicated elsewhere, so it stays its own query;
    only frame.now replaces its own datetime.now(timezone.utc) call."""

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_card_when_a_device_is_past_its_typical_max(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Garage light", 90, 60)

        daemon = SAEngine()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["priority"] == 2.6
        assert result["entity_name"] == "Garage light"
        assert result["deviation_type"] == "still_on_past_typical"
        assert "30 min" in result["content"]
        assert result["data"]["over_by_minutes"] == 30
        assert result["data"]["typical_daily_max_minutes"] == 60

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_no_device_exceeds_its_baseline(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        daemon = SAEngine()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_unusual_hour_card_when_no_still_on_deviation_but_hour_is_off(
        self, mock_connect
    ):
        """SA-10: second query (unusual_hour) is only reached once the first (still_on_past_
        typical) comes back empty."""
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, ("Garage light", 15, 0b111 << 12)]

        daemon = SAEngine()
        frame = _make_frame(now=datetime(2026, 10, 20, 3, 30, tzinfo=timezone.utc))
        result = daemon.check_rhythm_break_anomaly(frame)

        unusual_hour_params = mock_cursor.execute.call_args_list[1].args[1]
        assert unusual_hour_params == (0b111 << 2,)  # hours 02, 03, 04

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["deviation_type"] == "unusual_hour"
        assert result["entity_name"] == "Garage light"
        assert result["data"]["current_hour"] == 3
        assert result["data"]["typical_active_hour"] == 15

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_expected_absent_card_when_neither_prior_deviation_fires(self, mock_connect):
        """SA-10: third query (expected_absent) is only reached once both prior queries come
        back empty."""
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, None, ("Coffee maker", 8, 7)]

        daemon = SAEngine()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result["mode"] == "rhythm_break_anomaly"
        assert result["deviation_type"] == "expected_absent"
        assert result["entity_name"] == "Coffee maker"
        assert result["data"]["typical_active_hour"] == 7
        assert "hasn't come online" in result["content"]

        # A mocked cursor never validates the SQL, so check the placeholder count ourselves
        # (a 6-tuple against 7 %s made every cycle raise "not enough arguments for format string").
        sql, params = mock_cursor.execute.call_args_list[2].args
        assert sql.count("%s") == len(params)

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_all_three_deviation_queries_come_back_empty(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, None, None]

        daemon = SAEngine()
        result = daemon.check_rhythm_break_anomaly(_make_frame())

        assert result is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        daemon = SAEngine()
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
        from services.service_sa.sa.engine import _departure_hours_by_bucket

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
        from services.service_sa.sa.engine import _departure_hours_by_bucket

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
        from services.service_sa.sa.engine import _departure_hours_by_bucket

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
        from services.service_sa.sa.engine import _departure_hours_by_bucket

        assert _departure_hours_by_bucket([]) == {"weekday": [], "weekend": []}
        assert _departure_hours_by_bucket([datetime(2026, 8, 3, 6, 0)]) == {
            "weekday": [],
            "weekend": [],
        }

    def test_aggregates_multiple_days_into_the_right_bucket(self):
        from services.service_sa.sa.engine import _departure_hours_by_bucket

        timestamps = []
        for day_offset in range(7):  # a full week, so both buckets get real samples
            day = datetime(2026, 8, 3) + timedelta(days=day_offset)
            timestamps += _dense(day.replace(hour=2), day.replace(hour=7))
            timestamps.append(day.replace(hour=22))  # a same-day, unambiguous return

        buckets = _departure_hours_by_bucket(timestamps)

        assert len(buckets["weekday"]) == 5
        assert len(buckets["weekend"]) == 2
        assert all(hour == 7 for hour in buckets["weekday"] + buckets["weekend"])


class TestDeviceSessions:
    """Tests for _device_sessions()/_active_hours_mask(), compute_entity_baselines()'s helpers."""

    def test_a_lost_offline_transition_does_not_become_a_multi_day_session(self):
        """Regression: an offline row and an online row sharing one timestamp, then nothing for
        days (scanner idle over a weekend), used to read as one 3,800-minute session."""
        from services.service_sa.sa.engine import _device_sessions

        friday = datetime(2026, 10, 2, 20, 53)
        monday = datetime(2026, 10, 5, 12, 32)
        morning = friday - timedelta(hours=8)
        rows = [(morning + timedelta(minutes=30 * i), "online") for i in range(16)]
        rows += [
            (friday, "offline"),
            (friday, "online"),
            (monday, "offline"),
            (monday + timedelta(minutes=1), "online"),
        ]
        assert _device_sessions(rows) == [(morning, friday)]

    def test_a_gap_while_online_closes_the_session_at_the_last_row_seen_online(self):
        from services.service_sa.sa.engine import _device_sessions

        start = datetime(2026, 10, 6, 9, 0)
        rows = [(start + timedelta(minutes=m), "online") for m in range(0, 30)]
        rows.append((start + timedelta(hours=10), "online"))
        assert _device_sessions(rows) == [(start, start + timedelta(minutes=29))]

    def test_active_hours_cover_the_whole_workday_not_just_the_start_hour(self):
        from services.service_sa.sa.engine import _active_hours_mask

        sessions = [
            (datetime(2026, 10, d, 8, 45), datetime(2026, 10, d, 17, 5)) for d in range(5, 10)
        ]
        mask = _active_hours_mask(sessions)
        assert [h for h in range(24) if mask >> h & 1] == list(range(8, 18))

    def test_an_hour_reached_on_a_single_odd_day_is_not_part_of_the_usual_window(self):
        from services.service_sa.sa.engine import _active_hours_mask

        sessions = [
            (datetime(2026, 10, d, 9, 0), datetime(2026, 10, d, 12, 0)) for d in range(1, 11)
        ]
        sessions.append((datetime(2026, 10, 11, 1, 0), datetime(2026, 10, 11, 2, 0)))
        mask = _active_hours_mask(sessions)
        assert not mask >> 1 & 1 and mask >> 10 & 1


class TestComputeEntityBaselines:
    """Tests for compute_entity_baselines()."""

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_upserts_a_baseline_from_reconstructed_sessions(self, mock_connect, mock_tz):
        """Three online->offline pairs for one device should produce one
        upsert with the median/typical-hour/min/max derived from those
        three sessions, and a commit."""
        from services.service_sa.sa.engine import compute_entity_baselines

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
        # 3rd/4th/5th/6th fetchall(): SA-3's eligible-residents query (none eligible), SA-10's
        # household aggregate query (no rows), then SA-9 Phase 2's smarthome_sensor_history
        # query (no rows).
        mock_cursor.fetchall.side_effect = [[(42,)], sessions, [], [], []]

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
        assert params[3] == 1 << 9 | 1 << 10 | 1 << 11  # active_hours_mask (09:00-11:00 sessions)
        assert params[6] == 5  # sample_count
        mock_db.commit.assert_called_once()

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_skips_devices_below_minimum_sample_count(self, mock_connect, mock_tz):
        """A device with fewer than ENTITY_BASELINE_MIN_SAMPLES complete
        sessions must not get a baseline row -- too little history to be a
        real "typical" pattern yet."""
        from services.service_sa.sa.engine import compute_entity_baselines

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
        mock_cursor.fetchall.side_effect = [[(42,)], sessions, [], [], []]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 0
        mock_db.commit.assert_called_once()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_rolls_back_and_closes_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.engine import compute_entity_baselines

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
    tested above. See todo/sa/todo_departure_anomaly.md for the Phase 0 spike behind this."""

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_upserts_a_bucket_that_clears_the_floor_and_skips_one_that_doesnt(
        self, mock_connect, mock_tz
    ):
        """14 consecutive days -> 10 weekday departures (clears the 8-sample floor) and 4
        weekend departures (doesn't) -- weekday should get a row, weekend should not."""
        from services.service_sa.sa.engine import compute_entity_baselines

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
            [],  # SA-9 Phase 2 smarthome_sensor_history query
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

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_excludes_guests_from_the_eligible_residents_query(self, mock_connect, mock_tz):
        """The eligible-residents query itself (not a post-filter) must scope to
        owner/technoking/resident -- guests never even reach the departure computation. This
        test only asserts the query text, since the mocked cursor can't enforce real SQL
        filtering."""
        from services.service_sa.sa.engine import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0
        mock_cursor.fetchall.side_effect = [[], [], [], []]

        compute_entity_baselines()

        eligible_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "FROM user u" in call.args[0] and "JOIN user_types ut" in call.args[0]
        ]
        assert len(eligible_calls) == 1
        assert "'owner', 'technoking', 'resident'" in eligible_calls[0].args[0]

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_skips_a_user_with_no_claimed_devices(self, mock_connect, mock_tz):
        """An eligible (non-guest) user with zero rows in `device` must be skipped cleanly,
        not crash on an empty device_ids list."""
        from services.service_sa.sa.engine import compute_entity_baselines

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
            [],  # SA-9 Phase 2 smarthome_sensor_history query
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
    todo/sa/todo_generalize_entity_baselines.md for the real production-hardware timing that
    motivated keeping it that way."""

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_upserts_household_baselines_for_both_buckets(self, mock_connect, mock_tz):
        from services.service_sa.sa.engine import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        # (local_dow, first_hour, last_hour, device_count); MySQL DAYOFWEEK: 1=Sun...7=Sat.
        household_rows = [(2, 7, 22, 5)] * 15 + [  # 15 Mondays: weekday bucket
            (1, 9, 23, 3)
        ] * 15  # 15 Sundays: weekend bucket
        mock_cursor.fetchall.side_effect = [[], [], household_rows, []]

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

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_skips_a_bucket_below_the_sample_floor(self, mock_connect, mock_tz):
        from services.service_sa.sa.engine import (
            HOUSEHOLD_BASELINE_MIN_SAMPLES,
            compute_entity_baselines,
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        household_rows = [(2, 7, 22, 5)] * (HOUSEHOLD_BASELINE_MIN_SAMPLES - 1)
        mock_cursor.fetchall.side_effect = [[], [], household_rows, []]

        compute_entity_baselines()

        upsert_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0]
        ]
        assert len(upsert_calls) == 0
        mock_db.commit.assert_called_once()

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_household_aggregate_is_a_single_query_not_a_per_entity_loop(
        self, mock_connect, mock_tz
    ):
        """The whole point of computing this as a GROUP BY aggregate instead of a per-device
        Python loop -- confirm exactly one execute() call touches device_history for the
        household block, regardless of how many days of history exist."""
        from services.service_sa.sa.engine import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0
        mock_cursor.fetchall.side_effect = [[], [], [(2, 7, 22, 5)] * 20, []]

        compute_entity_baselines()

        household_query_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "GROUP BY local_date" in call.args[0]
        ]
        assert len(household_query_calls) == 1


class TestComputeClimateBaselines:
    """Tests for compute_entity_baselines()'s SA-9 Phase 2 addition: entity_type='room' rows
    built from smarthome_sensor_history, bucketed by common.timeofday.coarse_bucket() rather
    than day_bucket (weekday/weekend) -- see migration 041's own comment for why."""

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_upserts_a_climate_baseline_that_clears_the_floor(self, mock_connect, mock_tz):
        import statistics

        from services.service_sa.sa.engine import (
            CLIMATE_BASELINE_STDEV_MULTIPLIER,
            compute_entity_baselines,
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0  # UTC, so local_hour == recorded_at.hour

        # 10 readings at hour=14 ("day" bucket) for smarthome_device_id 5.
        base_day = datetime(2026, 8, 1, 14, 0)
        values = [float(20 + i) for i in range(10)]
        readings = [(5, v, base_day + timedelta(days=i)) for i, v in enumerate(values)]
        mock_cursor.fetchall.side_effect = [[], [], [], readings]

        compute_entity_baselines()

        climate_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0] and "'room'" in call.args[0]
        ]
        assert len(climate_calls) == 1
        params = climate_calls[0].args[1]
        median = statistics.median(values)
        stdev = statistics.stdev(values)
        assert params[0] == 5  # entity_id (smarthome_device_id)
        assert params[1] == "day"  # time_of_day_bucket
        assert params[2] == median  # typical_median_value (median of 20..29)
        # 2026-09-26 fix: typical_daily_min/max are a median +/- N-stdev band now, not the raw
        # observed min/max (20.0/29.0) -- see CLIMATE_BASELINE_STDEV_MULTIPLIER's own comment.
        assert params[3] == pytest.approx(median - CLIMATE_BASELINE_STDEV_MULTIPLIER * stdev)
        assert params[4] == pytest.approx(median + CLIMATE_BASELINE_STDEV_MULTIPLIER * stdev)
        assert params[5] == 10  # sample_count
        mock_db.commit.assert_called_once()

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_climate_band_is_tighter_than_the_raw_range_not_self_widening(
        self, mock_connect, mock_tz
    ):
        """The 2026-09-26 fix itself: a couple of outlier readings must not drag
        typical_daily_min/max out to the raw min/max, or the band is back to self-widening to
        cover everything and check_climate_deviation() can never fire again."""
        from services.service_sa.sa.engine import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        base_day = datetime(2026, 8, 1, 14, 0)
        # Tightly clustered around 25.0, plus two extreme outliers (15.0, 35.0).
        values = [25.0] * 18 + [15.0, 35.0]
        readings = [(5, v, base_day + timedelta(days=i)) for i, v in enumerate(values)]
        mock_cursor.fetchall.side_effect = [[], [], [], readings]

        compute_entity_baselines()

        climate_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0] and "'room'" in call.args[0]
        ]
        params = climate_calls[0].args[1]
        typical_min, typical_max = params[3], params[4]
        # The old (raw min/max) behavior would have set these to 15.0/35.0 -- exactly the
        # outliers, guaranteeing the band always contains any future reading in that range.
        assert typical_min > 15.0
        assert typical_max < 35.0

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_skips_a_bucket_below_the_sample_floor(self, mock_connect, mock_tz):
        from services.service_sa.sa.engine import (
            CLIMATE_BASELINE_MIN_SAMPLES,
            compute_entity_baselines,
        )

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        base_day = datetime(2026, 8, 1, 14, 0)
        readings = [
            (5, 22.0, base_day + timedelta(days=i)) for i in range(CLIMATE_BASELINE_MIN_SAMPLES - 1)
        ]
        mock_cursor.fetchall.side_effect = [[], [], [], readings]

        compute_entity_baselines()

        climate_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0] and "'room'" in call.args[0]
        ]
        assert len(climate_calls) == 0
        mock_db.commit.assert_called_once()

    @patch("services.service_sa.sa.engine.db_utils.get_env_timezone")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_buckets_readings_by_time_of_day_separately(self, mock_connect, mock_tz):
        """Morning and evening readings for the same entity must produce two independent
        baseline rows, not get averaged together into one."""
        from services.service_sa.sa.engine import compute_entity_baselines

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_tz.return_value = 0

        base_day = datetime(2026, 8, 1, 8, 0)  # hour=8 -> "morning"
        morning_readings = [(5, 18.0, base_day + timedelta(days=i)) for i in range(10)]
        evening_base = datetime(2026, 8, 1, 19, 0)  # hour=19 -> "evening"
        evening_readings = [(5, 23.0, evening_base + timedelta(days=i)) for i in range(10)]
        mock_cursor.fetchall.side_effect = [[], [], [], morning_readings + evening_readings]

        compute_entity_baselines()

        climate_calls = [
            call
            for call in mock_cursor.execute.call_args_list
            if "INSERT INTO entity_baselines" in call.args[0] and "'room'" in call.args[0]
        ]
        buckets = {call.args[1][1] for call in climate_calls}
        assert buckets == {"morning", "evening"}


class TestCheckDepartureAnomaly:
    """Tests for SAEngine.check_departure_anomaly() (SA-3). Not a frame field -- this
    entity_baselines/device/calendar_events join isn't duplicated elsewhere, so it stays its
    own query; only frame.local_dt/frame.day_mood/frame.now are shared."""

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_fires_when_overdue_home_and_no_calendar_event_explains_it(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]  # id, name, typical_hour, n
        mock_cursor.fetchone.side_effect = [(1,), None]  # online_count=1, no calendar event

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))  # Tuesday 3pm
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card["mode"] == "departure_anomaly"
        assert card["priority"] == 2.7
        assert card["entity_name"] == "Munja"
        assert "Munja" in card["content"]
        assert "Tuesday" in card["content"]
        assert card["data"]["typical_departure_hour"] == 8
        assert card["data"]["sample_count"] == 12
        assert card["data"]["because"]

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_no_baseline_candidates(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_cursor.fetchone.assert_not_called()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_before_the_grace_window_has_elapsed(self, mock_connect):
        """A resident whose current local hour hasn't yet cleared
        typical_hour + DEPARTURE_ANOMALY_GRACE_HOURS isn't overdue -- must not even reach the
        online-status check for that candidate."""
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 9, 0))  # only 1hr past typical_hour
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_cursor.fetchone.assert_not_called()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_resident_is_not_currently_home(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]
        mock_cursor.fetchone.return_value = (0,)  # no claimed device online

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_a_calendar_event_covers_right_now(self, mock_connect):
        """A booked morning at home (e.g. WFH) is not a deviation -- must not fire even
        though the resident is overdue and home."""
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12)]
        mock_cursor.fetchone.side_effect = [(1,), ("Working from home",)]

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_picks_the_most_overdue_resident_when_several_qualify(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        # Munja: 15:00 - 8:00 = 7h overdue. Vanja: 15:00 - 6:00 = 9h overdue -- more overdue.
        mock_cursor.fetchall.return_value = [(7, "Munja", 8, 12), (9, "Vanja", 6, 10)]
        mock_cursor.fetchone.side_effect = [(1,), (1,), None]  # both home, no calendar event

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card["entity_name"] == "Vanja"

    def test_returns_none_when_frame_is_missing_local_dt_or_day_mood(self):
        """No DB connection should even be attempted without frame.local_dt/day_mood."""
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            assert daemon.check_departure_anomaly(_make_frame(local_dt=None, day_mood=None)) is None
            mock_connect.assert_not_called()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        frame = _frame_with_day_mood(datetime(2026, 8, 11, 15, 0))
        daemon = SAEngine()
        card = daemon.check_departure_anomaly(frame)

        assert card is None
        mock_db.close.assert_called_once()


class TestCheckHouseholdUnusualDay:
    """SAEngine.check_household_unusual_day() reads the layer-2 inference (the LF-4 cutover,
    2026-10-12); the verdict itself is tested with the rule in test_sa_ports.py."""

    NOW = datetime(2026, 10, 12, 22, 0)

    def _inference(self):
        from services.service_sa.sa import layer2
        from services.service_sa.sa.learners import household_day
        from services.service_sa.sa.learners.base import Inference

        def row(feature, p, value, median):
            return Inference(
                kind="state",
                subject_type="household",
                subject_id=feature,
                signal=household_day.SIGNAL_FEATURE,
                learner=household_day.NAME,
                learner_version="2",
                window_start=self.NOW,
                observed={"value": value, "z": 3.0},
                expected={"median": median, "sigma": 1.0},
                probability=p,
                surprise=0.0,
                confidence=0.9,
                n_eff=30.0,
                evidence={"family": "household_day:" + feature, "feature": feature},
                context={"bar_bits": 2.0, "top_k": 5},  # the learned bar travels with the rows
            )

        rows = [row("device_share", 0.01, 0.3, 0.75), row("first_minute", 0.01, 700, 230)]
        rows.append(row("home_minutes", 0.9, 500, 500))
        return layer2.run_rules([household_day.RULE], rows, {}, self.NOW)[0]

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_a_fresh_inference_becomes_the_card(self, mock_connect, monkeypatch):
        from services.service_sa.sa import engine as engine_module

        monkeypatch.setattr(
            engine_module.inference_store, "load_recent", lambda *a, **k: [self._inference()]
        )
        frame = _frame_with_day_mood(self.NOW)

        card = engine_module.SAEngine().check_household_unusual_day(frame)

        assert card["mode"] == "household_unusual_day"
        assert card["priority"] == 6.5
        assert "Monday" in card["content"]
        assert card["data"]["because"]
        assert card["data"]["confidence"] > 0
        mock_connect.return_value.close.assert_called_once()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_no_inference_means_no_card(self, mock_connect, monkeypatch):
        from services.service_sa.sa import engine as engine_module

        monkeypatch.setattr(engine_module.inference_store, "load_recent", lambda *a, **k: [])

        assert (
            engine_module.SAEngine().check_household_unusual_day(_frame_with_day_mood(self.NOW))
            is None
        )

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_other_learners_layer_two_rows_are_not_this_card(self, mock_connect, monkeypatch):
        from services.service_sa.sa import engine as engine_module

        other = self._inference()
        other.learner = "away_unusual"
        monkeypatch.setattr(engine_module.inference_store, "load_recent", lambda *a, **k: [other])

        assert (
            engine_module.SAEngine().check_household_unusual_day(_frame_with_day_mood(self.NOW))
            is None
        )

    def test_returns_none_when_frame_is_missing_day_mood_or_now(self):
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect") as mock_connect:
            frame = _make_frame(local_dt=None, day_mood=None)
            assert SAEngine().check_household_unusual_day(frame) is None
            mock_connect.assert_not_called()

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value.execute.side_effect = pymysql.err.OperationalError("down")

        card = SAEngine().check_household_unusual_day(_frame_with_day_mood(self.NOW))

        assert card is None
        mock_db.close.assert_called_once()


class TestAttentionTelemetryTrend:
    """Tests for SAEngine._attention_telemetry_trend() (SA-2)."""

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_below_sample_floor(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(10, 2)] * 3

        assert SAEngine()._attention_telemetry_trend() is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_medians_at_or_above_sample_floor(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine, ATTENTION_TREND_MIN_SAMPLES

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        rows = [(10, 2)] * (ATTENTION_TREND_MIN_SAMPLES - 1) + [(30, 8)]
        mock_cursor.fetchall.return_value = rows

        trend = SAEngine()._attention_telemetry_trend()

        assert trend["sample_count"] == ATTENTION_TREND_MIN_SAMPLES
        assert trend["median_switch_count"] == 10
        assert trend["median_unlock_count"] == 2

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert SAEngine()._attention_telemetry_trend() is None


class TestCheckNowPlaying:
    """Tests for SAEngine.check_now_playing(). frame.playback/frame.persisted_now_playing
    (SA-4) replace what used to be a mocked live Spotify fetch and a mocked DB read --
    _write_now_playing_config()'s own DB write is unchanged, still needs pymysql mocked."""

    def _playback_state(self, track_id="track1", name="Song", artists=None, is_playing=True):
        return {
            "is_playing": is_playing,
            "item": {"id": track_id, "name": name, "artists": artists or ["Artist"]},
        }

    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_nothing_playing_returns_none_without_touching_db_or_producer(
        self, mock_connect, mock_producer
    ):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(playback={"is_playing": False, "item": None})
        daemon = SAEngine()
        result = daemon.check_now_playing(frame)

        assert result is None
        mock_connect.assert_not_called()
        mock_producer.assert_not_called()

    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_new_track_persists_state_and_publishes_event(self, mock_connect, mock_producer):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(playback=self._playback_state(), persisted_now_playing=None)

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1  # UPDATE "succeeds" -> no INSERT fallback

        mock_p = MagicMock()
        mock_producer.return_value = mock_p

        daemon = SAEngine()
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

    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_unchanged_track_does_not_rewrite_or_republish(self, mock_connect, mock_producer):
        """Same track_id + is_playing as last cycle must not spam config writes
        or event-stream messages every ~60s poll."""
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
        card = daemon.check_now_playing(frame)

        assert card is not None
        update_calls = [
            c for c in mock_cursor.execute.call_args_list if "UPDATE config" in c.args[0]
        ]
        assert len(update_calls) == 0
        mock_p.send.assert_not_called()

    @patch("services.service_sa.sa.engine.get_producer")
    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_pause_transition_persists_state_but_returns_no_card(self, mock_connect, mock_producer):
        """A track paused (item still present, is_playing False) must still
        get persisted to config -- check_cross_surface_continuity() depends
        on that "paused N minutes ago" state -- but produces no situational-
        awareness card and no event-stream announcement of its own."""
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        result = daemon.check_now_playing(_make_frame(playback=None))

        assert result is None


class TestCheckCrossSurfaceContinuity:
    """Tests for SAEngine.check_cross_surface_continuity(). frame.persisted_now_playing/
    frame.launcher_context.surface_state (SA-4) replace two of the three DB reads this rule
    used to make -- only the routines-edited query is still its own pymysql.connect() call."""

    @staticmethod
    def _config_dict(minutes_ago, **fields):
        return {
            **fields,
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
        }

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_offers_resume_for_a_recently_paused_track(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

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
        daemon = SAEngine()
        result = daemon.check_cross_surface_continuity(frame)

        assert result["mode"] == "cross_surface_continuity"
        assert result["resume_type"] == "music"
        assert result["resume_target"] == "track1"
        assert "Song" in result["content"]
        assert result["data"]["minutes_ago"] == 4

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_ignores_a_paused_track_older_than_staleness_window(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

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
        daemon = SAEngine()
        result = daemon.check_cross_surface_continuity(frame)

        assert result is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_picks_the_most_recent_of_multiple_candidates(self, mock_connect):
        """A terminal session reported 1 min ago must win over a track
        paused 10 min ago, even though the music check runs first."""
        from services.service_sa.sa.engine import SAEngine

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
        daemon = SAEngine()
        result = daemon.check_cross_surface_continuity(frame)

        assert result["resume_type"] == "terminal"

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_nothing_available(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        frame = _make_frame(
            persisted_now_playing={}, launcher_context=_make_launcher_context(surface_state={})
        )
        daemon = SAEngine()
        result = daemon.check_cross_surface_continuity(frame)

        assert result is None


class TestReadFreshAttentionTelemetry:
    """Tests for SAEngine._read_fresh_attention_telemetry() -- the staleness gate
    build_context_frame() calls once per cycle to populate
    frame.launcher_context.attention_snapshot. check_attention_focus()/
    check_wind_down_signal() only see the already-filtered result (None once stale),
    so this is where the staleness cutoff itself is covered."""

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_the_snapshot_when_fresh(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(5, switch_count=20)

        snapshot = SAEngine()._read_fresh_attention_telemetry()

        assert snapshot["switch_count"] == 20

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_snapshot_is_stale(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = _telemetry_row(120, switch_count=20)

        assert SAEngine()._read_fresh_attention_telemetry() is None

    @patch("services.service_sa.sa.engine.pymysql.connect")
    def test_returns_none_when_no_snapshot_reported_yet(self, mock_connect):
        from services.service_sa.sa.engine import SAEngine

        mock_cursor = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        assert SAEngine()._read_fresh_attention_telemetry() is None


class TestCheckAttentionFocus:
    """Tests for SAEngine.check_attention_focus() -- since the LF-4 cutover a card for the scalar
    learner's fresh HIGH `attention:switch_count` deviation. The snapshot supplies the displayed
    count and the media-dwell guard (both plain dicts built directly)."""

    def _inference(self, count=14, usual=2, direction="high", confidence=0.7, surprise=8.0,
                   series="attention:switch_count", learner="scalar_baseline"):  # fmt: skip
        import math
        from types import SimpleNamespace

        return SimpleNamespace(
            learner=learner,
            evidence={"series": series},
            observed={"value": math.log1p(count), "direction": direction},
            expected={"mu": math.log1p(usual), "sigma": 0.4, "z": 5.0},
            surprise=surprise,
            confidence=confidence,
        )

    def _frame(self, snapshot="default"):
        if snapshot == "default":
            snapshot = {"switch_count": 14, "dwell_by_category_ms": {"terminal": 600000}}
        return _make_frame(
            launcher_context=_make_launcher_context(attention_snapshot=snapshot, attention_trend=None)
        )

    def _check(self, recent, frame=None):
        from services.service_sa.sa.engine import SAEngine

        with (
            patch("services.service_sa.sa.engine.pymysql.connect"),
            patch(
                "services.service_sa.sa.engine.inference_store.load_recent", return_value=recent
            ),
        ):
            return SAEngine().check_attention_focus(frame or self._frame())

    def test_fires_on_a_high_deviation_that_is_not_media_heavy(self):
        result = self._check([self._inference()])

        assert result["mode"] == "attention_focus"
        assert result["priority"] == 3.6
        assert result["switch_count"] == 14
        assert result["content"] == "Deep in it — 14 window switches recently"
        assert result["data"]["typical_switch_count"] == 2
        assert result["data"]["because"][0] == "14 switches against about 2 usual at this hour"

    def test_a_quiet_hour_is_not_deep_focus(self):
        assert self._check([self._inference(direction="low")]) is None

    def test_low_confidence_stays_quiet(self):
        assert self._check([self._inference(confidence=0.1)]) is None

    def test_other_learners_and_series_are_ignored(self):
        recent = [
            self._inference(series="attention:unlock_count"),
            self._inference(learner="presence_profile"),
        ]
        assert self._check(recent) is None

    def test_returns_none_without_a_fresh_deviation(self):
        assert self._check([]) is None

    def test_returns_none_when_switching_is_media_heavy(self):
        """High switching while mostly dwelling in media is the wind-down pattern, not focus."""
        frame = self._frame({"switch_count": 20, "dwell_by_category_ms": {"media": 800000, "terminal": 100000}})  # fmt: skip

        assert self._check([self._inference()], frame) is None

    def test_returns_none_when_no_snapshot(self):
        """attention_snapshot is None whenever nothing fresh was reported."""
        assert self._check([self._inference()], self._frame(snapshot=None)) is None

    def test_the_most_surprising_deviation_is_used(self):
        recent = [self._inference(usual=2, surprise=5.0), self._inference(usual=6, surprise=9.0)]

        assert self._check(recent)["data"]["typical_switch_count"] == 6

    def test_returns_none_when_the_database_is_unreachable(self):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect", side_effect=pymysql.Error):
            assert SAEngine().check_attention_focus(self._frame()) is None


class TestCheckWindDownSignal:
    """Tests for SAEngine.check_wind_down_signal(). frame.day_mood/frame.launcher_context.
    attention_snapshot/.attention_trend (SA-4) replace what used to be mocked DB reads."""

    def test_fires_when_night_and_high_unlocks_and_media_heavy(self):
        from services.service_sa.sa.engine import SAEngine

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
        result = SAEngine().check_wind_down_signal(frame)

        assert result["mode"] == "wind_down_signal"
        assert result["priority"] == 5.8
        assert result["unlock_count"] == 8
        assert result["data"]["because"]

    def test_returns_none_when_not_night(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "day"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 8, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        assert SAEngine().check_wind_down_signal(frame) is None

    def test_returns_none_when_unlock_count_is_low(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 1, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        assert SAEngine().check_wind_down_signal(frame) is None

    def test_returns_none_when_dwell_is_not_media_heavy(self):
        from services.service_sa.sa.engine import SAEngine

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
        assert SAEngine().check_wind_down_signal(frame) is None

    def test_returns_none_when_no_snapshot(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(attention_snapshot=None, attention_trend=None),
        )
        assert SAEngine().check_wind_down_signal(frame) is None

    def test_uses_household_trend_once_enough_history_exists(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 6, "dwell_by_category_ms": {"media": 900000}},
                attention_trend={"median_switch_count": 2, "median_unlock_count": 8},
            ),
        )
        result = SAEngine().check_wind_down_signal(frame)

        assert result is None  # 6 < trend threshold (8 + 2 grace = 10)

    def test_fires_above_household_trend_threshold(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 12, "dwell_by_category_ms": {"media": 900000}},
                attention_trend={"median_switch_count": 2, "median_unlock_count": 8},
            ),
        )
        result = SAEngine().check_wind_down_signal(frame)

        assert result["unlock_count"] == 12

    def test_falls_back_to_fixed_threshold_when_no_trend(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            day_mood={"time_of_day": "night"},
            launcher_context=_make_launcher_context(
                attention_snapshot={"unlock_count": 6, "dwell_by_category_ms": {"media": 900000}},
                attention_trend=None,
            ),
        )
        result = SAEngine().check_wind_down_signal(frame)

        assert result["unlock_count"] == 6  # 6 >= fixed WIND_DOWN_MIN_UNLOCKS (5)


class TestCheckPartyAdvisory:
    """Tests for SAEngine.check_party_advisory(). frame.local_dt/frame.day_mood/
    frame.playback (SA-4) replace what used to be mocked get_env_local_time()/
    get_playback_state() calls."""

    @patch("services.service_sa.sa.engine.get_producer")
    @patch("common.spotify_utils.get_track_energy")
    @patch("services.service_sa.sa.engine.spotify_utils.is_party_night")
    def test_fires_for_high_energy_track_on_a_weeknight_night(
        self, mock_is_party_night, mock_get_track_energy, mock_get_producer
    ):
        from services.service_sa.sa.engine import SAEngine

        mock_is_party_night.return_value = False
        mock_get_track_energy.return_value = 0.9
        mock_get_producer.return_value = None

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Loud Song"}},
        )
        result = SAEngine().check_party_advisory(frame)

        assert result is not None
        assert result["mode"] == "party_advisory"
        assert result["priority"] == 3.2
        assert "Loud Song" in result["content"]
        assert result["data"]["track_name"] == "Loud Song"
        assert result["data"]["energy"] == 0.9
        assert result["data"]["day_of_week"] == "Tuesday"
        assert result["data"]["because"]

    @patch("services.service_sa.sa.engine.spotify_utils.is_party_night")
    def test_returns_none_on_a_declared_party_night(self, mock_is_party_night):
        from services.service_sa.sa.engine import SAEngine

        mock_is_party_night.return_value = True

        frame = _make_frame(
            local_dt=datetime(2026, 8, 14, 23, 30),  # Friday
            day_mood={"time_of_day": "night", "day_of_week": "Friday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Loud Song"}},
        )
        assert SAEngine().check_party_advisory(frame) is None

    def test_returns_none_when_frame_fields_missing(self):
        """frame.local_dt/frame.day_mood are None on a DB error building the frame --
        must not crash."""
        from services.service_sa.sa.engine import SAEngine

        assert SAEngine().check_party_advisory(_make_frame(local_dt=None, day_mood=None)) is None

    @patch("services.service_sa.sa.engine.spotify_utils.is_party_night")
    def test_returns_none_when_nothing_playing(self, mock_is_party_night):
        from services.service_sa.sa.engine import SAEngine

        mock_is_party_night.return_value = False

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": False, "item": None},
        )
        assert SAEngine().check_party_advisory(frame) is None

    @patch("common.spotify_utils.get_track_energy")
    @patch("services.service_sa.sa.engine.spotify_utils.is_party_night")
    def test_returns_none_when_energy_below_threshold(
        self, mock_is_party_night, mock_get_track_energy
    ):
        from services.service_sa.sa.engine import SAEngine

        mock_is_party_night.return_value = False
        mock_get_track_energy.return_value = 0.1

        frame = _make_frame(
            local_dt=datetime(2026, 8, 11, 23, 30),
            day_mood={"time_of_day": "night", "day_of_week": "Tuesday"},
            playback={"is_playing": True, "item": {"id": "track1", "name": "Chill Song"}},
        )
        assert SAEngine().check_party_advisory(frame) is None


class TestFocusUtils:
    """Tests for focus_utils.looks_like_call()."""

    def test_zoom_url_matches_at_probable_tier(self):
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call("https://us02web.zoom.us/j/123456", None) == PROBABLE

    def test_meet_google_url_matches_at_probable_tier(self):
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "Join here: https://meet.google.com/abc-defg-hij") == PROBABLE

    def test_teams_url_matches_at_probable_tier(self):
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call("https://teams.microsoft.com/l/meetup-join/xyz", None) == PROBABLE

    def test_bare_zoom_mention_matches_at_probable_tier(self):
        """Organizers sometimes paste a friendly label instead of a raw URL."""
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "Quick Zoom to review the roadmap") == PROBABLE

    def test_ordinary_address_and_notes_do_not_match(self):
        from services.service_sa.sa.focus_utils import looks_like_call

        assert looks_like_call("123 Main St", "Bring snacks") is None

    def test_no_address_or_notes_does_not_match(self):
        from services.service_sa.sa.focus_utils import looks_like_call

        assert looks_like_call(None, None) is None

    def test_matching_is_case_insensitive(self):
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "ZOOM.US/j/999") == PROBABLE
        assert looks_like_call(None, "Let's do a GOOGLE MEET") == PROBABLE

    def test_conference_uri_present_is_confirmed_regardless_of_text(self):
        """A real synced conference_uri (SA-7) is a confirmed call even when
        address/notes are empty or ordinary."""
        from services.service_sa.sa.focus_utils import looks_like_call, CONFIRMED

        assert looks_like_call(None, None, "https://meet.google.com/abc-defg-hij") == CONFIRMED
        assert looks_like_call("123 Main St", "Bring snacks", "https://zoom.us/j/1") == CONFIRMED

    def test_documented_false_positive_still_falls_to_probable_not_confirmed(self):
        """The documented false-positive case ("re-zoom the picture") must
        still only reach the probable tier -- text content alone can never
        promote a card to confirmed."""
        from services.service_sa.sa.focus_utils import looks_like_call, PROBABLE

        assert looks_like_call(None, "re-zoom the picture before the meeting", None) == PROBABLE

    def test_no_conference_uri_falls_back_to_text_heuristic(self):
        """An event with no conferencing data at all and ordinary text is
        neither confirmed nor probable."""
        from services.service_sa.sa.focus_utils import looks_like_call

        assert looks_like_call("123 Main St", "Bring snacks", None) is None


class TestCheckFocusNeeded:
    """Tests for SAEngine.check_focus_needed()."""

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
        from services.service_sa.sa.engine import SAEngine
        from services.service_sa.sa.focus_utils import PROBABLE

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, address="https://zoom.us/j/123", title="1:1 with Bob"
            )
        )
        daemon = SAEngine()
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
        from services.service_sa.sa.engine import SAEngine
        from services.service_sa.sa.focus_utils import CONFIRMED

        frame = _make_frame(
            upcoming_events=self._make_event(
                5,
                title="1:1 with Bob",
                conference_uri="https://meet.google.com/abc-defg-hij",
                conference_solution="Google Meet",
            )
        )
        daemon = SAEngine()
        card = daemon.check_focus_needed(frame)

        assert card is not None
        assert card["confidence"] == CONFIRMED
        assert card["conference_uri"] == "https://meet.google.com/abc-defg-hij"
        assert "Google Meet" in card["content"]
        assert "1:1 with Bob" in card["content"]

    def test_start_time_is_shown_in_household_local_time_not_utc(self):
        from services.service_sa.sa.engine import SAEngine

        now = datetime(2026, 9, 10, 14, 50, tzinfo=timezone.utc)
        frame = _make_frame(
            now=now,
            tz_offset=-4 * 3600,  # EDT
            upcoming_events=[
                {
                    "title": "1:1 with Bob",
                    "start_time": datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
                    "address": "https://zoom.us/j/123",
                    "notes": None,
                    "conference_uri": None,
                    "conference_solution": None,
                }
            ],
        )

        card = SAEngine().check_focus_needed(frame)

        assert card is not None
        assert "at 11:00 AM" in card["content"]  # 15:00 UTC - 4h
        assert "03:00 PM" not in card["content"]

    def test_documented_false_positive_fires_but_only_at_probable_tier(self):
        """ "re-zoom the picture" is a known false positive of the text
        heuristic -- it must still fire (accepted limitation of tier 2), but
        never be promoted to confirmed."""
        from services.service_sa.sa.engine import SAEngine
        from services.service_sa.sa.focus_utils import PROBABLE

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, notes="re-zoom the picture before the meeting", title="Photo review"
            )
        )
        daemon = SAEngine()
        card = daemon.check_focus_needed(frame)

        assert card is not None
        assert card["confidence"] == PROBABLE

    def test_pre_migration_event_with_null_conference_fields_does_not_error(self):
        """An event synced before this migration (or one predating
        get_upcoming_events() returning the new keys) has conference_uri/
        conference_solution as None -- must behave exactly like today, not
        raise."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            upcoming_events=self._make_event(
                5, address="https://zoom.us/j/123", title="1:1 with Bob"
            )
        )
        daemon = SAEngine()
        card = daemon.check_focus_needed(frame)

        assert card is not None

    def test_returns_none_when_outside_lead_time(self):
        """Matches, but starts well beyond FOCUS_LEAD_MINUTES away."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(upcoming_events=self._make_event(45, address="https://zoom.us/j/123"))
        daemon = SAEngine()
        assert daemon.check_focus_needed(frame) is None

    def test_returns_none_when_event_does_not_look_like_call(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            upcoming_events=self._make_event(5, address="123 Main St", notes="Bring donuts")
        )
        daemon = SAEngine()
        assert daemon.check_focus_needed(frame) is None

    def test_returns_none_when_no_upcoming_event(self):
        """Mirrors check_events()'s existing "no event" behavior."""
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
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
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
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

    def test_event_time_is_shown_in_household_local_time_not_utc(self):
        """calendar_events.start_time is stored/carried as UTC; the card's `content`
        string must be formatted in the household's local wall time (frame.to_local),
        or a CEST-authored event shows the wrong clock on an EST dashboard."""
        from services.service_sa.sa.engine import SAEngine

        now = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
        frame = _make_frame(
            now=now,
            tz_offset=-4 * 3600,  # America/Toronto, EDT
            upcoming_events=[
                {
                    "title": "Dentist",
                    "start_time": datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
                    "address": "123 Main St",
                    "notes": None,
                }
            ],
        )

        card = SAEngine().check_events(frame)

        assert "11:00 AM" in card["content"]  # 15:00 UTC - 4h
        assert "03:00 PM" not in card["content"]

    def test_returns_none_when_no_upcoming_event(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        assert daemon.check_events(_make_frame(upcoming_events=None)) is None

    def test_returns_none_when_event_more_than_three_hours_out(self):
        from services.service_sa.sa.engine import SAEngine

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

        daemon = SAEngine()
        assert daemon.check_events(frame) is None


class TestCheckTravel:
    """Tests for SAEngine.check_travel() (SA-6) -- restores what commit 08509ce removed, on
    self-hosted infrastructure. See todo/sa/todo_self_hosted_routing.md for the Phase 0 spike."""

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

    @patch("services.service_sa.sa.engine.routing_utils.get_route")
    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_fires_when_leave_by_is_not_yet_stale(self, mock_geocode, mock_home, mock_route):
        from services.service_sa.sa.engine import SAEngine

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 20, "distance_km": 12.3}

        # Event in 45 min, 20 min drive -> leave in 25 min, well before leave-by even arrives.
        frame = self._frame_with_event(now, minutes_to_start=45)
        daemon = SAEngine()
        card = daemon.check_travel(frame)

        assert card is not None
        assert card["mode"] == "travel"
        assert card["priority"] == 2.5
        assert "Dentist" in card["content"]
        assert card["data"]["duration_minutes"] == 20
        assert card["data"]["distance_km"] == 12.3
        assert card["data"]["traffic_aware"] is False
        assert card["data"]["because"]

    @patch("services.service_sa.sa.engine.routing_utils.get_route")
    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_leave_by_time_is_shown_in_household_local_time_not_utc(
        self, mock_geocode, mock_home, mock_route
    ):
        """leave_by is computed on the UTC timeline; the card's `content` must render it
        in the household's local wall time (frame.to_local)."""
        from services.service_sa.sa.engine import SAEngine

        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 20, "distance_km": 12.3}

        now = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
        frame = _make_frame(
            now=now,
            tz_offset=-4 * 3600,  # EDT
            upcoming_events=[
                {
                    "title": "Dentist",
                    "start_time": datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
                    "address": "100 Queen St W",
                    "notes": None,
                    "conference_uri": None,
                }
            ],
        )

        card = SAEngine().check_travel(frame)

        # 15:00 UTC start - 20 min drive = 14:40 UTC leave_by = 10:40 AM EDT
        assert card is not None
        assert "Leave by 10:40 AM for Dentist" == card["content"]

    def test_returns_none_when_no_upcoming_event(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        assert daemon.check_travel(_make_frame(upcoming_events=None)) is None

    def test_returns_none_when_address_is_blank(self):
        from services.service_sa.sa.engine import SAEngine

        now = datetime.now(timezone.utc)
        frame = self._frame_with_event(now, address="")
        daemon = SAEngine()
        assert daemon.check_travel(frame) is None

    def test_returns_none_for_a_conferencing_event_even_with_an_address(self):
        """A video call has nowhere to drive to -- check_focus_needed()'s job, not this one's."""
        from services.service_sa.sa.engine import SAEngine

        now = datetime.now(timezone.utc)
        frame = self._frame_with_event(now, conference_uri="https://meet.google.com/abc-defg-hij")
        daemon = SAEngine()
        assert daemon.check_travel(frame) is None

    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_returns_none_when_address_cannot_be_geocoded(self, mock_geocode):
        from services.service_sa.sa.engine import SAEngine

        mock_geocode.return_value = None
        now = datetime.now(timezone.utc)
        daemon = SAEngine()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_returns_none_when_home_location_not_set(self, mock_geocode, mock_home):
        from services.service_sa.sa.engine import SAEngine

        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = None
        now = datetime.now(timezone.utc)
        daemon = SAEngine()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_sa.sa.engine.routing_utils.get_route")
    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_returns_none_when_routing_service_unreachable(
        self, mock_geocode, mock_home, mock_route
    ):
        from services.service_sa.sa.engine import SAEngine

        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = None
        now = datetime.now(timezone.utc)
        daemon = SAEngine()
        assert daemon.check_travel(self._frame_with_event(now)) is None

    @patch("services.service_sa.sa.engine.routing_utils.get_route")
    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_fires_even_when_leave_by_is_far_in_the_future(
        self, mock_geocode, mock_home, mock_route
    ):
        """No upper bound on advance notice: self-hosted OSRM's estimate doesn't get more
        accurate closer to leave-by, so there's no reason to withhold a distant event's leave-by
        once it's computable -- when to actually surface it is alfr3d_deck's call
        (EventLeaveByLifecycle.LEAD_TIME_MINUTES), not this service's. See
        TRAVEL_STALE_AFTER_MINUTES's own doc comment for what changed and why."""
        from services.service_sa.sa.engine import SAEngine

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 5, "distance_km": 2.0}

        # Event in 3 hours, 5 min drive -> leave in ~175 min, well before leave-by even arrives.
        frame = self._frame_with_event(now, minutes_to_start=180)
        daemon = SAEngine()
        card = daemon.check_travel(frame)

        assert card is not None
        assert card["mode"] == "travel"
        assert card["data"]["leave_by"]

    @patch("services.service_sa.sa.engine.routing_utils.get_route")
    @patch("services.service_sa.sa.engine.routing_utils.fetch_home_coordinates")
    @patch("services.service_sa.sa.engine.routing_utils.geocode_address")
    def test_returns_none_once_leave_by_has_meaningfully_passed(
        self, mock_geocode, mock_home, mock_route
    ):
        """A stale leave-by time is worse than no card -- once it's TRAVEL_STALE_AFTER_MINUTES in
        the past, stop. (In real production traffic this can't actually happen --
        get_upcoming_events()'s own query only ever returns events starting at or after `now` --
        but check_travel() still guards it defensively rather than trusting that upstream
        invariant blindly.)"""
        from services.service_sa.sa.engine import SAEngine

        now = datetime.now(timezone.utc)
        mock_geocode.return_value = (43.65, -79.38)
        mock_home.return_value = (43.62, -79.55)
        mock_route.return_value = {"duration_minutes": 5, "distance_km": 2.0}

        # Event started 70 min ago, 5 min drive -> should have left 75 min ago, well past
        # TRAVEL_STALE_AFTER_MINUTES (30).
        frame = self._frame_with_event(now, minutes_to_start=-70)
        daemon = SAEngine()
        assert daemon.check_travel(frame) is None


class TestCheckWeatherAdvisory:
    """Tests for SAEngine.check_weather_advisory()."""

    def test_fires_when_rain_probability_exceeds_threshold(self):
        """frame.environment (SA-4) replaces this rule's own DB read."""
        from services.service_sa.sa.engine import (
            SAEngine,
            RAIN_ADVISORY_THRESHOLD,
            FORECAST_HOURS_AHEAD,
        )

        frame = _make_frame(environment={"forecast_rain_probability": RAIN_ADVISORY_THRESHOLD + 10})
        daemon = SAEngine()
        card = daemon.check_weather_advisory(frame)

        assert card is not None
        assert card["mode"] == "weather_advisory"
        assert card["priority"] == 4.5
        assert str(FORECAST_HOURS_AHEAD) in card["content"]
        assert "umbrella" in card["content"]
        assert card["data"]["forecast_rain_probability"] == RAIN_ADVISORY_THRESHOLD + 10
        assert card["data"]["hours_ahead"] == FORECAST_HOURS_AHEAD

    def test_returns_none_below_threshold(self):
        from services.service_sa.sa.engine import SAEngine, RAIN_ADVISORY_THRESHOLD

        frame = _make_frame(environment={"forecast_rain_probability": RAIN_ADVISORY_THRESHOLD - 5})
        daemon = SAEngine()
        assert daemon.check_weather_advisory(frame) is None

    def test_returns_none_when_forecast_not_yet_populated(self):
        """No forecast snapshot yet (NULL column) must not crash, just skip the card."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(environment={"forecast_rain_probability": None})
        daemon = SAEngine()
        assert daemon.check_weather_advisory(frame) is None

    def test_returns_none_when_no_environment_row(self):
        """frame.environment is None (no row, or a DB error building the frame) -- must
        not crash, same as check_weather()."""
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        assert daemon.check_weather_advisory(_make_frame(environment=None)) is None


class TestCheckClimateAdvisory:
    """Tests for SAEngine.check_climate_advisory() (SA-9 Phase 1)."""

    def _climate(self, **overrides):
        climate = {
            "temperature_c": 22.0,
            "temperature_online": True,
            "humidity_pct": 45,
            "humidity_online": True,
        }
        climate.update(overrides)
        return climate

    def test_returns_none_when_no_esphome_climate_on_frame(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        assert daemon.check_climate_advisory(_make_frame(esphome_climate=None)) is None

    def test_returns_none_within_comfort_band(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        frame = _make_frame(esphome_climate=self._climate())
        assert daemon.check_climate_advisory(frame) is None

    def test_fires_when_too_cold(self):
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_COLD_THRESHOLD_C,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(temperature_c=CLIMATE_ADVISORY_COLD_THRESHOLD_C - 1)
        )
        card = daemon.check_climate_advisory(frame)

        assert card["mode"] == "climate_advisory"
        assert card["priority"] == 5.3
        assert "cooler" in card["content"]
        assert card["data"]["temperature_c"] == CLIMATE_ADVISORY_COLD_THRESHOLD_C - 1

    def test_fires_when_too_hot(self):
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_HOT_THRESHOLD_C,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(temperature_c=CLIMATE_ADVISORY_HOT_THRESHOLD_C + 1)
        )
        card = daemon.check_climate_advisory(frame)

        assert card["mode"] == "climate_advisory"
        assert "warmer" in card["content"]
        assert card["data"]["temperature_c"] == CLIMATE_ADVISORY_HOT_THRESHOLD_C + 1

    def test_fires_when_humidity_too_high(self):
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(humidity_pct=CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT + 5)
        )
        card = daemon.check_climate_advisory(frame)

        assert card["mode"] == "climate_advisory"
        assert "higher" in card["content"]
        assert card["data"]["humidity_pct"] == CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT + 5

    def test_fires_when_humidity_too_low(self):
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_HUMIDITY_LOW_PCT,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(humidity_pct=CLIMATE_ADVISORY_HUMIDITY_LOW_PCT - 5)
        )
        card = daemon.check_climate_advisory(frame)

        assert card["mode"] == "climate_advisory"
        assert "lower" in card["content"]
        assert card["data"]["humidity_pct"] == CLIMATE_ADVISORY_HUMIDITY_LOW_PCT - 5

    def test_temperature_breach_wins_over_simultaneous_humidity_breach(self):
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_HOT_THRESHOLD_C,
            CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(
                temperature_c=CLIMATE_ADVISORY_HOT_THRESHOLD_C + 1,
                humidity_pct=CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT + 5,
            )
        )
        card = daemon.check_climate_advisory(frame)

        assert "temperature_c" in card["data"]
        assert "humidity_pct" not in card["data"]

    def test_ignores_a_stale_offline_temperature_reading(self):
        """A sensor's last known state must not fire an advisory once it's gone offline --
        smarthome_devices has no updated_at column, so `online` is the only freshness signal
        available this cycle."""
        from services.service_sa.sa.engine import (
            CLIMATE_ADVISORY_COLD_THRESHOLD_C,
            SAEngine,
        )

        daemon = SAEngine()
        frame = _make_frame(
            esphome_climate=self._climate(
                temperature_c=CLIMATE_ADVISORY_COLD_THRESHOLD_C - 1,
                temperature_online=False,
                humidity_pct=45,
                humidity_online=False,
            )
        )
        assert daemon.check_climate_advisory(frame) is None


class TestCheckClimateDeviation:
    """Tests for SAEngine.check_climate_deviation() -- since the LF-4 cutover a card for the scalar
    learner's fresh ESPHome temperature / humidity deviation; separate rule_id/mode from
    climate_advisory so dismissing one doesn't suppress the other."""

    TEMP = "esphome:athom-tem-hum-sensor-4a4734.local:Temperature"
    HUM = "esphome:athom-tem-hum-sensor-4a4734.local:Humidity"

    def _inference(self, series, value, direction, mu, surprise=14.0, confidence=0.8, learner=None):
        from types import SimpleNamespace

        return SimpleNamespace(
            learner=learner or "scalar_baseline",
            evidence={"series": series},
            observed={"value": value, "direction": direction},
            expected={"mu": mu, "sigma": 0.8, "z": 4.5},
            surprise=surprise,
            confidence=confidence,
        )

    def _check(self, recent):
        from services.service_sa.sa.engine import SAEngine

        with (
            patch("services.service_sa.sa.engine.pymysql.connect"),
            patch(
                "services.service_sa.sa.engine.inference_store.load_recent", return_value=recent
            ),
        ):
            return SAEngine().check_climate_deviation(_make_frame())

    def test_returns_none_without_a_fresh_deviation(self):
        assert self._check([]) is None

    def test_cooler_temperature_card(self):
        card = self._check([self._inference(self.TEMP, 21.9, "low", 26.5)])

        assert card["mode"] == "climate_deviation"
        assert card["priority"] == 5.4
        assert card["content"] == "Cooler than typical for this time of day (21.9°C)"
        assert card["data"]["temperature_c"] == 21.9
        assert card["data"]["typical_median_value"] == 26.5

    def test_warmer_temperature_card(self):
        card = self._check([self._inference(self.TEMP, 31.0, "high", 26.5)])

        assert "Warmer" in card["content"]

    def test_humidity_cards(self):
        low = self._check([self._inference(self.HUM, 20.0, "low", 45.0)])
        high = self._check([self._inference(self.HUM, 70.0, "high", 45.0)])

        assert "Lower humidity" in low["content"] and low["data"]["humidity_pct"] == 20.0
        assert "Higher humidity" in high["content"]

    def test_low_confidence_stays_quiet(self):
        """A series whose stability was just cut by a regime change must not show a card."""
        assert self._check([self._inference(self.TEMP, 21.9, "low", 26.5, confidence=0.04)]) is None

    def test_other_learners_and_series_are_ignored(self):
        recent = [
            self._inference(self.TEMP, 21.9, "low", 26.5, learner="presence_profile"),
            self._inference("attention:switch_count", 30, "high", 2),
            self._inference("speedtest:download", 3.0, "low", 90.0),
        ]

        assert self._check(recent) is None

    def test_the_most_surprising_deviation_wins_with_temperature_on_a_tie(self):
        recent = [
            self._inference(self.HUM, 70.0, "high", 45.0, surprise=9.0),
            self._inference(self.TEMP, 21.9, "low", 26.5, surprise=9.0),
        ]
        assert "temperature_c" in self._check(recent)["data"]

        recent[0] = self._inference(self.HUM, 70.0, "high", 45.0, surprise=20.0)
        assert "humidity_pct" in self._check(recent)["data"]

    def test_returns_none_when_the_database_is_unreachable(self):
        import pymysql
        from services.service_sa.sa.engine import SAEngine

        with patch("services.service_sa.sa.engine.pymysql.connect", side_effect=pymysql.Error):
            assert SAEngine().check_climate_deviation(_make_frame()) is None


class TestCheckTime:
    """Tests for SAEngine.check_time() -- previously exercised only indirectly
    via decide_displays() stubs, never as its own real (unmocked) call."""

    def test_returns_well_formed_time_card(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        card = daemon.check_time(_make_frame())

        assert card["mode"] == "time"
        assert card["priority"] == 1
        # content is a real ISO-8601 timestamp, not a placeholder string.
        datetime.fromisoformat(card["content"])

    def test_shares_the_frames_timestamp_not_its_own(self):
        """SA-4 acceptance criterion: all cards in one cycle share a single timestamp."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(now=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        daemon = SAEngine()
        card = daemon.check_time(frame)

        assert card["content"] == "2026-01-01T12:00:00+00:00"


class TestCheckWeather:
    """Tests for SAEngine.check_weather() -- previously exercised only via
    decide_displays() stubs, never with a real DB-backed call."""

    def test_returns_formatted_weather_card(self):
        """frame.environment (SA-4) replaces this rule's own DB read."""
        from services.service_sa.sa.engine import SAEngine

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
        daemon = SAEngine()
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
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        assert daemon.check_weather(_make_frame(environment=None)) is None


class TestCheckEmails:
    """Tests for SAEngine.check_emails() -- previously exercised only via
    decide_displays() stubs; gmail_utils.check_unread_emails() itself is a
    placeholder that always returns None, so the "emails found" branch of
    check_emails() had never actually run under test."""

    @patch("services.service_sa.sa.engine.gmail_utils.check_unread_emails")
    def test_returns_card_summarizing_first_unread_email(self, mock_check_unread):
        from services.service_sa.sa.engine import SAEngine

        mock_check_unread.return_value = [
            {"sender": "boss@example.com", "subject": "Q3 numbers"},
            {"sender": "friend@example.com", "subject": "Lunch?"},
        ]

        daemon = SAEngine()
        card = daemon.check_emails(_make_frame())

        assert card["mode"] == "email"
        assert card["priority"] == 4
        assert "boss@example.com" in card["content"]
        assert "Q3 numbers" in card["content"]
        assert "Total Unread: 2" in card["content"]

    @patch("services.service_sa.sa.engine.gmail_utils.check_unread_emails")
    def test_returns_none_when_no_unread_emails(self, mock_check_unread):
        from services.service_sa.sa.engine import SAEngine

        mock_check_unread.return_value = None

        daemon = SAEngine()
        assert daemon.check_emails(_make_frame()) is None


class TestContextFrameToLocal:
    """Tests for ContextFrame.to_local() -- renders a UTC datetime in the household's
    local wall time for card `content` strings (calendar_events.start_time is UTC)."""

    def test_applies_the_household_offset(self):
        from services.service_sa.sa.context_frame import ContextFrame

        frame = ContextFrame()
        frame.tz_offset = -4 * 3600  # EDT
        utc = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

        local = frame.to_local(utc)

        assert local.strftime("%I:%M %p") == "11:00 AM"
        assert local.utcoffset() == timedelta(hours=-4)

    def test_passes_through_unchanged_when_offset_unknown(self):
        from services.service_sa.sa.context_frame import ContextFrame

        frame = ContextFrame()  # tz_offset defaults to None
        utc = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

        assert frame.to_local(utc) is utc

    def test_handles_none(self):
        from services.service_sa.sa.context_frame import ContextFrame

        frame = ContextFrame()
        frame.tz_offset = -4 * 3600
        assert frame.to_local(None) is None


class TestContextFrameFetchers:
    """Tests for context_frame.py's standalone fetchers (SA-4) -- both new for this
    refactor, neither existed as a reusable function before."""

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_online_devices_splits_known_and_unknown(self, mock_connect):
        from services.service_sa.sa.context_frame import fetch_online_devices

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

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_online_devices_treats_alfr3d_owned_as_infrastructure(self, mock_connect):
        """Devices owned by the `alfr3d` system user (smart speakers, camera, hub, router)
        are the house's own gear: not members, and not "unrecognized" either."""
        from services.service_sa.sa.context_frame import fetch_online_devices

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("athos", "Athos's Phone"),
            ("alfr3d", "Google Home Mini"),
            ("alfr3d", "C200"),
            ("alfr3d", "Router"),
        ]

        result = fetch_online_devices()

        assert result["known_names"] == ["athos"]
        assert result["known_count"] == 1
        assert result["unknown_count"] == 0
        assert result["infrastructure_count"] == 3

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_online_devices_counts_unknown_owner_and_unowned_as_unrecognized(
        self, mock_connect
    ):
        from services.service_sa.sa.context_frame import fetch_online_devices

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("athos", "Athos's Phone"),
            ("unknown", "Claimed-as-unknown"),
            (None, "Unowned"),
            ("alfr3d", "Router"),
        ]

        result = fetch_online_devices()

        assert result["unknown_count"] == 2
        assert result["infrastructure_count"] == 1

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_online_devices_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.context_frame import fetch_online_devices

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_online_devices() is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_smarthome_online_returns_sorted_names(self, mock_connect):
        from services.service_sa.sa.context_frame import fetch_smarthome_online

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("Living Room Lamp",), ("Garage Heater",)]

        assert fetch_smarthome_online() == ["Garage Heater", "Living Room Lamp"]

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_smarthome_online_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.context_frame import fetch_smarthome_online

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_smarthome_online() is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_a_dict(self, mock_connect):
        from services.service_sa.sa.context_frame import fetch_environment_snapshot

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

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_none_when_no_row(self, mock_connect):
        from services.service_sa.sa.context_frame import fetch_environment_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        assert fetch_environment_snapshot("test_env") is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_environment_snapshot_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa.context_frame import fetch_environment_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_environment_snapshot("test_env") is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_snapshot_returns_a_dict(self, mock_connect):
        import orjson

        from services.service_sa.sa.context_frame import fetch_esphome_climate_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (
                "Temperature",
                1,
                orjson.dumps({"state": 24.9, "attributes": {"unit_of_measurement": "°C"}}),
            ),
            (
                "Humidity",
                1,
                orjson.dumps({"state": 60.9, "attributes": {"unit_of_measurement": "%"}}),
            ),
        ]

        result = fetch_esphome_climate_snapshot()

        assert result == {
            "temperature_c": 24.9,
            "temperature_online": True,
            "humidity_pct": 60.9,
            "humidity_online": True,
        }

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_snapshot_ignores_a_wifi_signal_percent_row(self, mock_connect):
        """A WiFi-signal sensor can also report a '%' unit -- the fetcher matches by name
        substring, not unit, so it must not mistake a wifi-signal-percent row for humidity."""
        import orjson

        from services.service_sa.sa.context_frame import fetch_esphome_climate_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (
                "WiFi Signal Percent",
                1,
                orjson.dumps({"state": 100, "attributes": {"unit_of_measurement": "%"}}),
            ),
            (
                "Humidity",
                1,
                orjson.dumps({"state": 60.9, "attributes": {"unit_of_measurement": "%"}}),
            ),
        ]

        result = fetch_esphome_climate_snapshot()

        assert result["humidity_pct"] == 60.9

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_snapshot_returns_none_when_no_matching_rows(self, mock_connect):
        from services.service_sa.sa.context_frame import fetch_esphome_climate_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        assert fetch_esphome_climate_snapshot() is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_snapshot_returns_none_on_db_error(self, mock_connect):
        import pymysql

        from services.service_sa.sa.context_frame import fetch_esphome_climate_snapshot

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_esphome_climate_snapshot() is None

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_baselines_returns_a_dict(self, mock_connect):
        from services.service_sa.sa.context_frame import (
            fetch_esphome_climate_baselines,
        )

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("Temperature", 22.5, 20.0, 25.0, 12, 10),
            ("Humidity", 45.0, 40.0, 50.0, 12, 10),
        ]

        result = fetch_esphome_climate_baselines("day")

        assert result == {
            "temperature": {
                "typical_median_value": 22.5,
                "typical_daily_min": 20.0,
                "typical_daily_max": 25.0,
                "sample_count": 12,
                "min_sample_count": 10,
            },
            "humidity": {
                "typical_median_value": 45.0,
                "typical_daily_min": 40.0,
                "typical_daily_max": 50.0,
                "sample_count": 12,
                "min_sample_count": 10,
            },
        }

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_baselines_returns_none_values_when_no_baseline_yet(
        self, mock_connect
    ):
        from services.service_sa.sa.context_frame import (
            fetch_esphome_climate_baselines,
        )

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = fetch_esphome_climate_baselines("night")

        assert result == {"temperature": None, "humidity": None}

    @patch("services.service_sa.sa.context_frame.pymysql.connect")
    def test_fetch_esphome_climate_baselines_returns_none_on_db_error(self, mock_connect):
        import pymysql

        from services.service_sa.sa.context_frame import (
            fetch_esphome_climate_baselines,
        )

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert fetch_esphome_climate_baselines("day") is None


class TestRoutingUtils:
    """Tests for routing_utils.py (SA-6) -- the self-hosted routing/geocoding client
    check_travel() depends on. See todo/sa/todo_self_hosted_routing.md for the Phase 0 spike that
    justified this design."""

    @patch("services.service_sa.sa.routing_utils._write_geocode_cache")
    @patch("services.service_sa.sa.routing_utils._read_geocode_cache")
    def test_geocode_address_returns_cached_coordinates_without_calling_nominatim(
        self, mock_read_cache, mock_write_cache
    ):
        from services.service_sa.sa import routing_utils

        mock_read_cache.return_value = (43.65, -79.38)

        with patch("services.service_sa.sa.routing_utils.requests.get") as mock_get:
            result = routing_utils.geocode_address("100 Queen St W, Toronto")

        assert result == (43.65, -79.38)
        mock_get.assert_not_called()
        mock_write_cache.assert_not_called()

    @patch("services.service_sa.sa.routing_utils._write_geocode_cache")
    @patch("services.service_sa.sa.routing_utils._read_geocode_cache")
    def test_geocode_address_returns_none_for_a_cached_not_found_without_requerying(
        self, mock_read_cache, mock_write_cache
    ):
        """A row exists (address was looked up before) but latitude/longitude are NULL -- a
        cached "not found", distinct from no cache row at all. Must not hit Nominatim again."""
        from services.service_sa.sa import routing_utils

        mock_read_cache.return_value = (None, None)

        with patch("services.service_sa.sa.routing_utils.requests.get") as mock_get:
            result = routing_utils.geocode_address("not a real address")

        assert result is None
        mock_get.assert_not_called()
        mock_write_cache.assert_not_called()

    @patch("services.service_sa.sa.routing_utils._write_geocode_cache")
    @patch("services.service_sa.sa.routing_utils._read_geocode_cache")
    @patch("services.service_sa.sa.routing_utils.requests.get")
    def test_geocode_address_calls_nominatim_on_a_cache_miss_and_writes_the_result(
        self, mock_get, mock_read_cache, mock_write_cache
    ):
        from services.service_sa.sa import routing_utils

        mock_read_cache.return_value = None  # no cache row at all
        mock_get.return_value.json.return_value = [{"lat": "43.65", "lon": "-79.38"}]
        mock_get.return_value.raise_for_status = MagicMock()

        result = routing_utils.geocode_address("100 Queen St W, Toronto")

        assert result == (43.65, -79.38)
        assert mock_get.call_args.kwargs["headers"]["User-Agent"]
        mock_write_cache.assert_called_once_with("100 Queen St W, Toronto", (43.65, -79.38))

    @patch("services.service_sa.sa.routing_utils._write_geocode_cache")
    @patch("services.service_sa.sa.routing_utils._read_geocode_cache")
    @patch("services.service_sa.sa.routing_utils.requests.get")
    def test_geocode_address_caches_a_not_found_result_too(
        self, mock_get, mock_read_cache, mock_write_cache
    ):
        from services.service_sa.sa import routing_utils

        mock_read_cache.return_value = None
        mock_get.return_value.json.return_value = []  # Nominatim found nothing
        mock_get.return_value.raise_for_status = MagicMock()

        result = routing_utils.geocode_address("nowhere in particular")

        assert result is None
        mock_write_cache.assert_called_once_with("nowhere in particular", None)

    def test_geocode_address_returns_none_for_a_blank_address(self):
        from services.service_sa.sa import routing_utils

        assert routing_utils.geocode_address("") is None
        assert routing_utils.geocode_address(None) is None
        assert routing_utils.geocode_address("   ") is None

    @patch("services.service_sa.sa.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_a_tuple(self, mock_connect):
        from services.service_sa.sa import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (43.65, -79.38)

        assert routing_utils.fetch_home_coordinates("test_env") == (43.65, -79.38)

    @patch("services.service_sa.sa.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_none_when_location_not_set(self, mock_connect):
        from services.service_sa.sa import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (None, None)

        assert routing_utils.fetch_home_coordinates("test_env") is None

    @patch("services.service_sa.sa.routing_utils.pymysql.connect")
    def test_fetch_home_coordinates_returns_none_on_db_error(self, mock_connect):
        import pymysql
        from services.service_sa.sa import routing_utils

        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = pymysql.err.OperationalError("db down")

        assert routing_utils.fetch_home_coordinates("test_env") is None

    @patch("services.service_sa.sa.routing_utils.requests.get")
    def test_get_route_returns_duration_and_distance(self, mock_get):
        from services.service_sa.sa import routing_utils

        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "code": "Ok",
            "routes": [{"duration": 1180.1, "distance": 17941.4}],
        }

        result = routing_utils.get_route((43.62, -79.55), (43.65, -79.38))

        assert result["duration_minutes"] == 1180.1 / 60
        assert result["distance_km"] == 17941.4 / 1000

    @patch("services.service_sa.sa.routing_utils.requests.get")
    def test_get_route_returns_none_when_no_route_found(self, mock_get):
        from services.service_sa.sa import routing_utils

        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"code": "NoRoute", "routes": []}

        assert routing_utils.get_route((43.62, -79.55), (43.65, -79.38)) is None

    @patch("services.service_sa.sa.routing_utils.requests.get")
    def test_get_route_returns_none_when_service_unreachable(self, mock_get):
        import requests

        from services.service_sa.sa import routing_utils

        mock_get.side_effect = requests.exceptions.ConnectionError("routing container down")

        assert routing_utils.get_route((43.62, -79.55), (43.65, -79.38)) is None


class TestBuildContextFrame:
    """Tests for SAEngine.build_context_frame() (SA-4) -- in particular the acceptance
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
    @patch("services.service_sa.sa.engine.calendar_utils.get_upcoming_events")
    @patch("services.service_sa.sa.engine.context_frame.fetch_environment_snapshot")
    @patch("services.service_sa.sa.engine.db_utils.get_env_local_time")
    def test_a_spotify_failure_does_not_prevent_unrelated_fields_from_building(
        self, mock_get_local_time, mock_fetch_environment, mock_get_events, mock_playback
    ):
        from services.service_sa.sa.engine import SAEngine

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

        frame = SAEngine().build_context_frame()

        assert frame.playback is None  # the simulated failure
        assert frame.now is not None
        assert frame.day_mood is not None
        assert frame.environment["city"] == "Testville"

        daemon = SAEngine()
        assert daemon.check_time(frame) is not None
        assert daemon.check_weather(frame) is not None
        assert daemon.check_events(frame) is None  # no events, but doesn't crash
        assert daemon.check_now_playing(frame) is None  # no playback, but doesn't crash


class TestCheckEmptyHouseStillOn:
    """Tests for SAEngine.check_empty_house_still_on() (SA-4 Phase 3) -- the rule that
    needs three frame fields at once (online_devices, smarthome_online, day_mood) and
    couldn't have been written before the context frame existed."""

    def test_fires_when_house_empty_smarthome_on_and_evening(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices([(None, "Unclaimed Device")]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        result = SAEngine().check_empty_house_still_on(frame)

        assert result["mode"] == "empty_house_still_on"
        assert result["priority"] == 2.4
        assert "Living Room Lamp" in result["content"]
        assert result["device_count"] == 1
        assert result["data"]["smarthome_device_names"] == ["Living Room Lamp"]
        assert result["data"]["because"]

    def test_returns_none_when_a_claimed_device_is_online(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices([("athos", "Athos's Phone")]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        assert SAEngine().check_empty_house_still_on(frame) is None

    def test_returns_none_when_nothing_smarthome_is_on(self):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices([]),
            smarthome_online=[],
            day_mood={"time_of_day": "evening"},
        )
        assert SAEngine().check_empty_house_still_on(frame) is None

    def test_returns_none_during_the_day(self):
        """Not noteworthy during the day -- 'everyone's out, something's on' is the
        normal daytime state, not an anomaly."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=_online_devices([]),
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "day"},
        )
        assert SAEngine().check_empty_house_still_on(frame) is None

    def test_returns_none_when_online_devices_is_none(self):
        """frame.online_devices is None on a DB error building the frame -- must not
        crash."""
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            online_devices=None,
            smarthome_online=["Living Room Lamp"],
            day_mood={"time_of_day": "evening"},
        )
        assert SAEngine().check_empty_house_still_on(frame) is None


class TestPublishSA:
    """Tests for SAEngine.publish_sa()."""

    @patch("services.service_sa.sa.engine.get_producer")
    def test_sends_data_to_situational_awareness_topic(self, mock_get_producer):
        from services.service_sa.sa.engine import SAEngine

        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        daemon = SAEngine()
        daemon.publish_sa([{"mode": "time", "content": "t", "priority": 1}])

        assert mock_producer.send.call_args[0][0] == "situational-awareness"

    @patch("services.service_sa.sa.engine.get_producer")
    def test_no_crash_when_producer_unavailable(self, mock_get_producer):
        """No Kafka producer (e.g. broker unreachable) must not raise."""
        from services.service_sa.sa.engine import SAEngine

        mock_get_producer.return_value = None

        daemon = SAEngine()
        daemon.publish_sa([{"mode": "time", "content": "t", "priority": 1}])  # must not raise


class TestCheckSituationalAwareness:
    """Tests for SAEngine.check_situational_awareness(), the orchestration
    method that ties decide_displays() and publish_sa() together."""

    def test_publishes_when_displays_are_returned(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        cards = [{"mode": "time", "content": "t", "priority": 1}]
        daemon.decide_displays = MagicMock(return_value=cards)
        daemon.publish_sa = MagicMock()

        daemon.check_situational_awareness()

        daemon.publish_sa.assert_called_once_with(cards)

    def test_does_not_publish_when_no_displays_fire(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        daemon.decide_displays = MagicMock(return_value=[])
        daemon.publish_sa = MagicMock()

        daemon.check_situational_awareness()

        daemon.publish_sa.assert_not_called()


# --- Phase 2: device-context uplink consumption (todo_context_exchange_protocol.md) --


class TestDeviceContextRollup:
    """SAEngine._read_fresh_device_contexts() / ._any_device_in_dnd() -- the staleness gate
    and the household reduce over N reporting Decks."""

    def _daemon(self):
        from services.service_sa.sa.engine import SAEngine

        return SAEngine()

    def _stored(self, devices):
        return {"schema_version": 1, "devices": devices}

    def _entry(self, facets, age_minutes=0):
        observed = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        return {"facets": facets, "observed_at": observed.isoformat()}

    def test_fresh_device_is_returned(self):
        daemon = self._daemon()
        stored = self._stored({"dev-a": self._entry({"interruption": {"dnd_active": True}})})
        with patch.object(daemon, "_read_config_json", return_value=stored):
            assert "dev-a" in daemon._read_fresh_device_contexts()

    def test_stale_device_is_dropped(self):
        """A stale DND reading is worse than none -- it would keep claiming the user is
        silenced long after they stopped being."""
        daemon = self._daemon()
        stored = self._stored(
            {"dev-a": self._entry({"interruption": {"dnd_active": True}}, age_minutes=99)}
        )
        with patch.object(daemon, "_read_config_json", return_value=stored):
            assert daemon._read_fresh_device_contexts() == {}

    def test_nothing_reported_is_empty_not_an_error(self):
        daemon = self._daemon()
        with patch.object(daemon, "_read_config_json", return_value={}):
            assert daemon._read_fresh_device_contexts() == {}

    def test_unparseable_timestamp_is_skipped(self):
        daemon = self._daemon()
        stored = self._stored(
            {"dev-a": {"facets": {"power": {"is_charging": True}}, "observed_at": "nonsense"}}
        )
        with patch.object(daemon, "_read_config_json", return_value=stored):
            assert daemon._read_fresh_device_contexts() == {}

    def test_dnd_rollup_is_any_not_last_writer(self):
        """The stated reduce: one Deck in DND means the household has silenced
        interruptions somewhere, regardless of what the other Deck says."""
        daemon = self._daemon()
        contexts = {
            "dev-a": {"interruption": {"dnd_active": False}},
            "dev-b": {"interruption": {"dnd_active": True}},
        }
        assert daemon._any_device_in_dnd(contexts) is True

    def test_dnd_rollup_false_when_every_device_reports_off(self):
        daemon = self._daemon()
        contexts = {"dev-a": {"interruption": {"dnd_active": False}}}
        assert daemon._any_device_in_dnd(contexts) is False

    def test_dnd_rollup_none_when_facet_never_reported(self):
        """Tri-state: "nobody told us" must stay distinguishable from "told us it's off",
        or a rule softens its advice on the strength of a device nobody asked about."""
        daemon = self._daemon()
        assert daemon._any_device_in_dnd({}) is None
        assert daemon._any_device_in_dnd({"dev-a": {"power": {"is_charging": True}}}) is None


class TestFocusNeededDndCorrelation:
    """check_focus_needed()'s Phase 2 consumer behavior -- the deferred follow-up
    todo_attention_telemetry.md asked for."""

    def _event(self, minutes_out=5):
        start = datetime.now(timezone.utc) + timedelta(minutes=minutes_out)
        return {
            "title": "Design review",
            "address": "https://meet.google.com/abc-defg-hij",
            "notes": "",
            "conference_uri": "https://meet.google.com/abc-defg-hij",
            "start_time": start,
        }

    def _card(self, device_contexts):
        from services.service_sa.sa.engine import SAEngine

        frame = _make_frame(
            upcoming_events=[self._event()],
            launcher_context=_make_launcher_context(device_contexts=device_contexts),
        )
        return SAEngine().check_focus_needed(frame)

    def test_dnd_off_keeps_the_quiet_spot_advice(self):
        card = self._card({"dev-a": {"interruption": {"dnd_active": False}}})
        assert card is not None
        assert "Find a quiet spot." in card["content"]
        assert card["dnd_active"] is False

    def test_dnd_on_replaces_advice_the_user_already_took(self):
        card = self._card({"dev-a": {"interruption": {"dnd_active": True}}})
        assert "Do Not Disturb is already on." in card["content"]
        assert "Find a quiet spot." not in card["content"]
        assert "a Deck reports Do Not Disturb on" in card["data"]["because"]

    def test_dnd_on_still_fires_the_card(self):
        """The useful part is "your call starts in N minutes" -- silencing that because the
        phone is silenced would throw away the alert to preserve the footnote."""
        card = self._card({"dev-a": {"interruption": {"dnd_active": True}}})
        assert card is not None
        assert card["mode"] == "focus_needed"
        assert "Design review" in card["content"]

    def test_no_device_reporting_is_unchanged_from_before_phase_2(self):
        card = self._card({})
        assert "Find a quiet spot." in card["content"]
        assert card["dnd_active"] is None


class TestSystemHealth:
    """check_system_health(): debounced, rate-limited probe of configured integrations."""

    @pytest.fixture(autouse=True)
    def _fresh_state(self):
        from services.service_sa.sa import engine

        engine.SYSTEM_HEALTH_STATE.clear()
        yield
        engine.SYSTEM_HEALTH_STATE.clear()

    @staticmethod
    def _run(ha=(True, False), st=(False, False), now=1000.0, daemon=None):
        """Run one check. ha/st = (configured, connected); st defaults to unconfigured."""
        from services.service_sa.sa.engine import SAEngine

        daemon = daemon or SAEngine()
        with patch("common.ha_utils.is_ha_configured", return_value=ha[0]), patch(
            "common.ha_utils.test_ha_connection", return_value=(ha[1], "m")
        ), patch("common.st_utils.is_st_configured", return_value=st[0]), patch(
            "common.st_utils.test_st_connection", return_value=(st[1], "m")
        ), patch(
            "services.service_sa.sa.engine.time.time", return_value=now
        ):
            return daemon.check_system_health(None)

    def test_single_failed_probe_does_not_alert(self):
        assert self._run(now=1000.0) is None

    def test_second_consecutive_failure_fires_urgent_card(self):
        self._run(now=1000.0)
        card = self._run(now=1000.0 + 301)
        assert card["mode"] == "system_health"
        assert card["urgent"] is True
        assert card["data"]["unreachable"] == ["home_assistant"]
        assert "Home Assistant" in card["content"]

    def test_probes_are_rate_limited_between_cycles(self):
        self._run(now=1000.0)
        # Next 60s cycle: inside the probe interval, so no second failure is counted.
        assert self._run(now=1060.0) is None

    def test_recovery_clears_the_alert(self):
        self._run(now=1000.0)
        assert self._run(now=1301.0) is not None
        assert self._run(ha=(True, True), now=1602.0) is None

    def test_unconfigured_integration_never_alerts(self):
        for i in range(4):
            assert self._run(ha=(False, False), now=1000.0 + 301 * i) is None

    def test_probe_exception_is_not_counted_as_down(self):
        from services.service_sa.sa.engine import SAEngine

        daemon = SAEngine()
        with patch("common.ha_utils.is_ha_configured", side_effect=RuntimeError("db down")), patch(
            "common.st_utils.is_st_configured", return_value=False
        ):
            for i in range(4):
                with patch(
                    "services.service_sa.sa.engine.time.time",
                    return_value=1000.0 + 301 * i,
                ):
                    assert daemon.check_system_health(None) is None

    def test_urgent_card_survives_a_recent_dismissal(self):
        """The card's `urgent` flag must route it past decide_displays()'s suppression pass."""
        from services.service_sa.sa.engine import CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD

        assert CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD == "urgent"


class TestAwarenessEntrypoint:
    """service_sa/awareness.py: the 60s card loop that used to run inside service_daemon."""

    def test_cycle_runs_situational_awareness_and_survives_a_failure(self):
        from services.service_sa import awareness

        engine = MagicMock()
        engine.check_situational_awareness.side_effect = [RuntimeError("boom"), None]
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise KeyboardInterrupt

        with patch.object(awareness.heartbeat, "touch") as touch, patch.object(
            awareness.time, "sleep", side_effect=fake_sleep
        ), pytest.raises(KeyboardInterrupt):
            awareness.run(engine)

        assert engine.check_situational_awareness.call_count == 2
        assert sleeps == [awareness.CYCLE_SECONDS, awareness.CYCLE_SECONDS]
        assert touch.call_count == 2


class TestLearnerEntrypoint:
    """service_sa/learner.py: compute_entity_baselines() on the daemon's old 6h cadence."""

    def test_baselines_scheduled_every_six_hours(self):
        import schedule

        from services.service_sa import learner

        schedule.clear()
        try:
            schedule.every(learner.BASELINE_INTERVAL_HOURS).hours.do(
                learner.engine.compute_entity_baselines
            )
            (job,) = schedule.get_jobs()
            assert job.interval == 6 and job.unit == "hours"
        finally:
            schedule.clear()

    def test_daemon_no_longer_schedules_baselines_or_sa(self):
        import inspect

        with patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "localhost:9092"}):
            from services.service_daemon import alfr3ddaemon

        assert not hasattr(alfr3ddaemon, "compute_entity_baselines")
        assert not hasattr(alfr3ddaemon.MyDaemon, "check_situational_awareness")
        assert "compute_entity_baselines)" not in inspect.getsource(alfr3ddaemon.init_daemon)
