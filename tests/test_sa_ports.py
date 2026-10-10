"""Tests for the learners that replace the legacy baselines (device rhythm, household day) and the
shadow runner that compares them with the legacy rules (sa/shadow.py)."""

import random
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from services.service_sa.sa import shadow
from services.service_sa.sa.learners import device_rhythm, household_day, presence, scalar
from services.service_sa.sa.learners.base import Profile

REF = date(2026, 10, 9)  # a Friday


def _rows(days, online_when):
    """(date, hour, dow, minutes_online, observed) rows for `days` days ending at REF."""
    rows, d = [], REF - timedelta(days=days - 1)
    while d <= REF:
        for h in range(24):
            rows.append((d, h, d.weekday(), 60.0 if online_when(d, h) else 0.0, True))
        d += timedelta(days=1)
    return rows


def _sessions(days, minutes_fn):
    out, d = [], REF - timedelta(days=days - 1)
    while d <= REF:
        out.append((d, minutes_fn(d), datetime.combine(d, datetime.min.time())))
        d += timedelta(days=1)
    return out


class TestDeviceRhythm:
    def _profile(self):
        rows = _rows(40, lambda d, h: 8 <= h < 22)
        sessions = _sessions(40, lambda d: 840 + (d.day % 5) * 10)
        return device_rhythm.DeviceRhythmLearner().fit_device(7, "Lamp", rows, sessions, REF, None)

    def test_a_device_with_no_recent_sessions_gets_no_profile(self):
        rows = _rows(40, lambda d, h: False)
        assert device_rhythm.DeviceRhythmLearner().fit_device(7, "x", rows, [], REF, None) is None

    def test_on_in_the_small_hours_is_unusual_hour(self):
        profile = self._profile()
        now = datetime(2026, 10, 10, 7, 0)
        inf = device_rhythm.DeviceRhythmLearner().score(
            profile,
            {"online": True, "offline_minutes": None, "local_dt": datetime(2026, 10, 10, 3, 0)},
            now,
        )
        assert inf is not None and inf.signal == "device.online"
        assert inf.expected["p_online"] < 0.15 and inf.surprise >= 3

    def test_off_when_normally_on_is_expected_absent_but_only_after_an_hour(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        local = datetime(2026, 10, 10, 14, 0)
        now = datetime(2026, 10, 10, 18, 0)
        assert (
            learner.score(profile, {"online": False, "offline_minutes": 20, "local_dt": local}, now)
            is None
        )
        inf = learner.score(
            profile, {"online": False, "offline_minutes": 90, "local_dt": local}, now
        )
        assert inf.observed["state"] == "offline"

    def test_a_device_offline_for_days_or_retired_is_not_late(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        local, now = datetime(2026, 10, 10, 14, 0), datetime(2026, 10, 10, 18, 0)
        state = {"online": False, "offline_minutes": 5 * 24 * 60, "local_dt": local}
        assert learner.score(profile, state, now) is None
        rows = _rows(40, lambda d, h: 8 <= h < 22)
        old = [(d, m, end - timedelta(days=30)) for d, m, end in _sessions(40, lambda d: 840)]
        assert learner.fit_device(7, "Old", rows, old, REF, None) is None

    def test_normal_state_is_quiet(self):
        profile = self._profile()
        inf = device_rhythm.DeviceRhythmLearner().score(
            profile,
            {"online": True, "offline_minutes": None, "local_dt": datetime(2026, 10, 10, 14, 0)},
            datetime(2026, 10, 10, 18, 0),
        )
        assert inf is None

    def test_a_session_far_longer_than_any_past_one_fires(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        now = datetime(2026, 10, 10, 18, 0)
        local = datetime(2026, 10, 10, 14, 0)
        assert learner.score_duration(profile, {"minutes_on": 850, "local_dt": local}, now) is None
        inf = learner.score_duration(profile, {"minutes_on": 3000, "local_dt": local}, now)
        assert inf is not None and inf.observed["minutes_on"] == 3000 and inf.probability < 0.02

    def test_survival_is_smoothed_away_from_zero_and_one(self):
        d = [(100.0, 1.0)] * 10
        assert 0 < device_rhythm.survival(d, 10_000) < 0.1
        assert device_rhythm.survival(d, 0) < 1


class TestHouseholdDay:
    def _days(self, n=45, devices=lambda d: 26, first=lambda d: 230.0):
        out, d = [], REF - timedelta(days=n - 1)
        rnd = random.Random(3)
        while d <= REF:
            out.append(
                {
                    "date": d,
                    "devices": devices(d) + rnd.choice([-1, 0, 0, 1]),
                    "first_minute": first(d) + rnd.choice([-10, 0, 10]),
                }
            )
            d += timedelta(days=1)
        return out

    def _score(self, profile, devices, first):
        state = {
            "devices": devices,
            "first_minute": first,
            "local_dt": datetime(2026, 10, 12, 18, 0),
        }
        return household_day.HouseholdDayLearner().score(
            profile, state, datetime(2026, 10, 12, 22, 0)
        )

    def test_too_little_history_gives_no_profile(self):
        assert household_day.HouseholdDayLearner().fit_days(self._days(10), REF) is None

    def test_a_normal_day_is_quiet(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        assert self._score(profile, 26, 230) is None

    def test_a_day_odd_on_both_features_is_a_layer_2_deviation_with_its_parents(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        inf = self._score(profile, 12, 700)
        assert inf.layer == 2 and inf.signal == "household.day"
        assert {p["feature"] for p in inf.evidence["parents"]} == {"devices", "first_minute"}
        assert inf.probability <= household_day.P_FLAG and 0 < inf.confidence <= 1

    def test_one_odd_feature_alone_is_not_enough(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        assert self._score(profile, 26, 700) is None  # normal device count, odd first activity
        assert self._score(profile, 8, 230) is None  # odd device count, normal first activity

    def test_fisher_combines_mild_evidence(self):
        assert household_day.fisher_p([0.05, 0.05], [1, 1]) < 0.05
        assert household_day.fisher_p([0.5, 0.5], [1, 1]) > 0.5
        # low confidence weights the evidence down
        assert household_day.fisher_p([0.001, 0.001], [0.1, 0.1]) > household_day.fisher_p(
            [0.001, 0.001], [1, 1]
        )


class TestShadowRunner:
    def _runner(self):
        persisted = []
        return shadow.ShadowRunner(MagicMock(), persisted.extend), persisted

    def test_logs_only_when_the_pair_changes(self, caplog):
        runner, _ = self._runner()
        caplog.set_level("INFO", logger="SALog")
        runner.record("climate_deviation", "quiet", [])
        runner.record("climate_deviation", "quiet", [])
        assert sum("SHADOW" in r.message for r in caplog.records) == 1
        runner.record("climate_deviation", "climate_deviation:", [])
        assert "DIFFER" in caplog.records[-1].message

    def test_findings_are_persisted_and_marked_agree_when_both_fire(self, caplog):
        runner, persisted = self._runner()
        caplog.set_level("INFO", logger="SALog")
        pts = [
            {
                "t": datetime(2026, 9, 1) + timedelta(hours=i),
                "date": (
                    date(2026, 9, 1) + timedelta(hours=i // 24 * 24 // 24)
                    if False
                    else (datetime(2026, 9, 1) + timedelta(hours=i)).date()
                ),
                "hour": (i % 24),
                "value": 20.0 + (i % 5) * 0.1,
                "coverage": 1.0,
            }
            for i in range(24 * 10)
        ]
        profile = scalar.fit_points("s", pts, pts[-1]["date"])
        inf = scalar.ScalarLearner().score(
            profile,
            {
                "value": 40.0,
                "recent": [(l, (24 - l) % 24, 20.2) for l in range(1, 25)],
                "local_dt": datetime(2026, 9, 11, 3, 0),
            },
            datetime(2026, 9, 11, 3, 0),
        )
        assert inf is not None
        runner.record("climate_deviation", "climate_deviation:", [inf])
        assert persisted == [inf] and "AGREE" in caplog.records[-1].message

    def test_an_exception_in_a_comparison_never_escapes(self, caplog):
        runner, _ = self._runner()
        runner.climate = MagicMock(side_effect=RuntimeError("db down"))
        runner.run(MagicMock(), {"climate_deviation": None})
        assert any("SHADOW climate_deviation failed" in r.message for r in caplog.records)

    def test_only_rules_the_engine_ran_are_compared(self):
        runner, _ = self._runner()
        runner.climate = MagicMock(return_value=[])
        runner.run(MagicMock(), {"time": None})
        runner.climate.assert_not_called()

    def test_departure_compares_people_still_home_with_the_presence_profile(self):
        runner, _ = self._runner()
        rows = []
        for i in range(24 * 40):
            day, hour = REF - timedelta(days=i // 24), i % 24
            at_home = day.weekday() < 5 and not 9 <= hour < 17
            rows.append((day, hour, day.weekday(), 60.0 if at_home else 0.0, True))
        profile = presence.PresenceLearner().fit_user(1, "athos", rows, [], REF)
        runner._profiles[presence.NAME] = ("x", [profile])
        runner._connect = MagicMock()
        frame = MagicMock()
        frame.person_presence = [
            {"user_id": 1, "home": True, "user_type": "owner", "last_online": None}
        ]
        frame.local_dt = datetime(2026, 10, 9, 11, 0)  # Friday, mid-workday
        frame.now = datetime(2026, 10, 9, 15, 0)
        runner.profiles = lambda name: [profile]
        findings = runner.departure(frame)
        assert findings and findings[0].observed["state"] == "home"

    def test_rhythm_ignores_an_offline_row_replaced_by_an_online_row_of_the_same_name(self):
        runner, _ = self._runner()
        profile = TestDeviceRhythm()._profile()
        profile.subject_id = "4"
        runner.profiles = lambda name: [profile]
        now = datetime(2026, 10, 10, 18, 0)
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (4, "offline", now - timedelta(hours=14), "Phone"),
            (137, "online", now - timedelta(minutes=1), "Phone"),
        ]
        runner._connect = lambda: MagicMock(cursor=lambda: cursor)
        frame = MagicMock()
        frame.local_dt, frame.now = datetime(2026, 10, 10, 14, 0), now
        assert runner.rhythm(frame) == []
