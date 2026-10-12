"""Daytime-at-home learner (sa/learners/daytime.py): more hours at home today than comparable days,
judged at the day level, so a part-time resident's ordinary day at home is not a day off."""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "service_sa"))

from sa import layer2  # noqa: E402
from sa.learners import daytime, day_off  # noqa: E402
from sa.shadow import ShadowRunner  # noqa: E402

REF = date(2026, 10, 9)  # a Friday
TODAY = datetime(2026, 10, 12, 14, 0)  # Monday 14:00 local (Thanksgiving, an off day)


def _rows(pattern):
    """Observed hourly rows for the 80 days before REF: pattern(day) -> hours at home in 09-17."""
    rows = []
    for i in range(80):
        day = REF - timedelta(days=i)
        home_hours = pattern(day)
        for hour in range(24):
            at_home = 9 <= hour < 9 + home_hours
            rows.append((day, hour, day.weekday(), 60.0 if at_home else 0.0, True))
    return rows


def _profile(pattern):
    return daytime.DaytimeLearner().fit_user(1, "x", _rows(pattern), REF, 0.95, 0.8, 1.0)


def _score(profile, hours_home, local_dt=TODAY):
    return daytime.DaytimeLearner().score(
        profile,
        {"hours_home": hours_home, "local_dt": local_dt, "day_start": datetime(2026, 10, 12, 4)},
        datetime(2026, 10, 12, 18),
    )


class TestDaytimeLearner:
    def test_a_day_at_home_for_someone_who_is_always_out_is_flagged(self):
        profile = _profile(lambda day: 0)

        found = _score(profile, 4.0)

        assert found is not None and found.surprise >= daytime.MIN_SURPRISE_BITS
        assert found.observed["state"] == "home" and found.signal == daytime.SIGNAL

    def test_a_day_at_home_is_ordinary_for_someone_who_is_often_home(self):
        # Home 5 h on every fifth day: four hours at home is not unusual for this person.
        profile = _profile(lambda day: 5 if day.toordinal() % 5 == 0 else 0)

        assert _score(profile, 4.0) is None

    def test_no_time_at_home_so_far_is_never_a_day_off(self):
        assert _score(_profile(lambda day: 0), 0.0) is None

    def test_nothing_is_scored_before_the_first_checkpoint(self):
        profile = _profile(lambda day: 0)

        assert _score(profile, 2.0, local_dt=datetime(2026, 10, 12, 11, 0)) is None

    def test_too_few_observed_days_gives_no_profile(self):
        rows = [r for r in _rows(lambda day: 0) if r[0] > REF - timedelta(days=5)]

        assert daytime.DaytimeLearner().fit_user(1, "x", rows, REF, 0.9, 0.8, 1.0) is None

    def test_weekdays_and_off_days_are_judged_against_their_own_kind(self):
        # Always home on weekends and holidays, always out on weekdays.
        profile = _profile(lambda day: 6 if daytime.presence.is_offday(day) else 0)

        assert _score(profile, 5.0, local_dt=TODAY) is None  # TODAY is a holiday
        assert _score(profile, 5.0, local_dt=datetime(2026, 10, 13, 14, 0)) is not None  # Tuesday


class TestDaytimeFeedsDayOff:
    def test_the_layer_one_row_becomes_the_layer_two_inference(self):
        profile = _profile(lambda day: 0)
        parent = _score(profile, 4.0)
        parent.row_id = 7
        ctx = {"day_start_utc": datetime(2026, 10, 12, 4), "calendar_events_today": 0}

        out = layer2.run_rules([day_off.RULE], [parent], ctx, datetime(2026, 10, 12, 18))

        assert len(out) == 1 and out[0].signal == day_off.SIGNAL
        assert layer2.family_of(parent) == "network"

    def test_every_row_fits_the_sa_inferences_columns(self):
        parent = _score(_profile(lambda day: 0), 4.0)

        assert len(parent.subject_type) <= 16 and len(parent.signal) <= 48
        assert len(parent.learner) <= 48 and len(parent.learner_version) <= 16


class TestShadowDaytimeRows:
    def _runner(self, profile, sightings):
        cursor = MagicMock()
        cursor.fetchall.return_value = sightings
        db = MagicMock()
        db.cursor.return_value = cursor
        persisted = []
        runner = ShadowRunner(lambda: db, persisted.extend)
        runner.profiles = lambda name: [profile]
        return runner, persisted, cursor

    def _frame(self, local_dt=TODAY):
        return SimpleNamespace(
            now=datetime(2026, 10, 12, 18, 0),
            local_dt=local_dt,
            person_presence=[{"user_id": 1, "home": True, "user_type": "resident"}],
        )

    def test_a_resident_home_through_the_window_is_scored_and_persisted(self):
        profile = _profile(lambda day: 0)
        # A sighting every 30 minutes from 09:00 to 14:00 local (13:00 to 18:00 UTC).
        sightings = [
            (1, datetime(2026, 10, 12, 13, 0) + timedelta(minutes=30 * i)) for i in range(11)
        ]
        runner, persisted, _ = self._runner(profile, sightings)

        rows = runner.daytime_rows(self._frame())

        assert len(rows) == 1 and persisted == rows
        assert rows[0].observed["hours_home"] >= 4.0

    def test_a_cached_row_is_refreshed_each_cycle_so_layer_two_keeps_seeing_it(self):
        profile = _profile(lambda day: 0)
        sightings = [
            (1, datetime(2026, 10, 12, 13, 0) + timedelta(minutes=30 * i)) for i in range(11)
        ]
        runner, persisted, cursor = self._runner(profile, sightings)
        first = runner.daytime_rows(self._frame())[0]
        stale = datetime(2026, 1, 1)
        first.computed_at = stale

        again = runner.daytime_rows(self._frame())[0]

        assert again is first and again.computed_at > stale
        assert cursor.execute.call_count == 1  # one device_history pass per checkpoint hour

    def test_guests_and_morning_hours_are_skipped(self):
        profile = _profile(lambda day: 0)
        runner, _, cursor = self._runner(profile, [])
        guest = self._frame()
        guest.person_presence = [{"user_id": 1, "home": True, "user_type": "guest"}]

        assert runner.daytime_rows(guest) == []
        assert runner.daytime_rows(self._frame(datetime(2026, 10, 12, 10, 0))) == []
        cursor.execute.assert_not_called()
