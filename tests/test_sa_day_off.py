"""Tests for the layer-2 day_off rule and the calendar observer (LF-6)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.service_sa.sa import layer2, shadow
from services.service_sa.sa.learners import day_off, presence
from services.service_sa.sa.learners.base import Inference

NOW = datetime(2026, 10, 12, 15, 0)
DAY_START = datetime(2026, 10, 12, 4, 0)


def _home_dev(p=2**-5, conf=0.5, subject="1"):
    return Inference(
        kind="deviation",
        subject_type="user",
        subject_id=subject,
        signal=presence.SIGNAL,
        learner="presence_profile",
        learner_version="1",
        window_start=NOW.replace(minute=0),
        observed={"state": "home"},
        probability=p,
        surprise=5.0,
        confidence=conf,
        evidence={"username": "athos"},
        context={"hour_local": 11},
    )


class TestDayOffRule:
    def test_empty_calendar_keeps_full_confidence_and_windows_the_whole_day(self):
        ctx = {"day_start_utc": DAY_START, "calendar_events_today": 0}

        out = layer2.run_rules([day_off.RULE], [_home_dev()], ctx, NOW)

        assert len(out) == 1 and out[0].signal == day_off.SIGNAL
        assert out[0].confidence == 0.5 and out[0].window_start == DAY_START
        assert out[0].evidence["calendar_events_today"] == 0

    def test_a_booked_day_cuts_confidence_to_the_floor(self):
        ctx = {"day_start_utc": DAY_START, "calendar_events_today": 3}

        out = layer2.run_rules([day_off.RULE], [_home_dev()], ctx, NOW)

        assert abs(out[0].confidence - 0.5 * day_off.CORROBORATION_FLOOR) < 1e-3

    def test_no_calendar_count_is_uncorroborated_not_penalised(self):
        out = layer2.run_rules([day_off.RULE], [_home_dev()], {}, NOW)

        assert out[0].confidence == 0.5

    def test_an_away_deviation_is_not_a_day_off(self):
        away = _home_dev()
        away.observed = {"state": "away"}

        assert layer2.run_rules([day_off.RULE], [away], {}, NOW) == []


class TestCalendarState:
    def test_a_covering_event_becomes_a_state_row_without_its_title(self):
        start, end = NOW - timedelta(hours=1), NOW + timedelta(hours=1)
        cursor = MagicMock()
        cursor.fetchall.return_value = [(9, start, end)]
        db = MagicMock()
        db.cursor.return_value = cursor
        persisted = []
        runner = shadow.ShadowRunner(lambda: db, persisted.extend)

        found = runner.calendar_state(SimpleNamespace(now=NOW.replace(tzinfo=timezone.utc)))

        assert persisted == found and len(found) == 1
        row = found[0]
        assert row.kind == "state" and row.signal == layer2.SIGNAL_CALENDAR_BUSY
        assert row.window_start == start and row.evidence == {"family": "calendar", "event_id": 9}
        assert "SELECT id, start_time, end_time" in cursor.execute.call_args[0][0]


class TestShadowHouseholdComparison:
    def test_the_layer_two_result_is_logged_against_the_legacy_card(self, monkeypatch, caplog):
        import logging

        from services.service_sa.sa.learners import household_day

        db = MagicMock()
        db.cursor.return_value = MagicMock()
        runner = shadow.ShadowRunner(lambda: db, lambda inferences: None)
        runner.profiles = lambda name: []
        monkeypatch.setattr(shadow.inference_store, "load_recent", lambda *a, **k: [])
        frame = SimpleNamespace(now=NOW.replace(tzinfo=timezone.utc), local_dt=None)

        with caplog.at_level(logging.INFO, logger="SALog"):
            runner.layer2(frame, {"household_unusual_day": None})

        assert any(
            "SHADOW household_unusual_day AGREE" in r.getMessage() for r in caplog.records
        ), household_day.RULE.legacy_rule
