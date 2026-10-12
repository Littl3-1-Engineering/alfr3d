"""Tests for the layer-2 away_unusual combiner and its shadow wiring (LF-6)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.service_sa.sa import shadow
from services.service_sa.sa.learners import away_unusual, device_rhythm, presence
from services.service_sa.sa.learners.base import Inference

NOW = datetime(2026, 10, 9, 15, 0)


def _inf(signal, p, conf, subject="1", state="away", family=None, **kw):
    return Inference(
        kind="deviation",
        subject_type="user",
        subject_id=subject,
        signal=signal,
        learner="x",
        learner_version="1",
        window_start=NOW - timedelta(hours=3),
        observed={"state": state, "away_minutes": 180.0},
        expected={"p_home": 0.9},
        probability=p,
        surprise=0.0,
        confidence=conf,
        n_eff=10.0,
        evidence={"family": family} if family else {},
        context={"hour_local": 11},
        **kw,
    )


def _presence(p=0.05, conf=0.4):
    return _inf(presence.SIGNAL, p, conf)


def _device(subject, p=0.05, conf=0.5):
    return _inf(device_rhythm.SIGNAL_AVAILABILITY, p, conf, subject=subject, state="offline")


class TestCombine:
    def test_presence_alone_is_one_vote_and_keeps_its_probability_and_confidence(self):
        out = away_unusual.combine("1", "athos", _presence(), [], 0, NOW)

        assert out.layer == 2 and out.signal == away_unusual.SIGNAL
        assert out.probability == 0.05 and out.confidence == 0.4
        assert out.evidence["corroboration"] is None and out.evidence["families"] == ["network"]

    def test_devices_in_the_same_family_do_not_add_surprise(self):
        devices = [_device("7", p=0.04), _device("8", p=0.04)]
        out = away_unusual.combine("1", "athos", _presence(p=0.05), devices, 2, NOW)

        assert out.probability == 0.04  # the most surprising of one family, not a product
        assert out.evidence["method"] == "single_family"

    def test_corroboration_scales_confidence_not_probability(self):
        lone = away_unusual.combine("1", "a", _presence(), [_device("7")], 4, NOW)
        full = away_unusual.combine(
            "1", "a", _presence(), [_device(str(i)) for i in range(4)], 4, NOW
        )

        assert lone.probability == full.probability
        assert lone.confidence < full.confidence
        assert full.confidence > 0.4 * 0.99  # all owned devices quiet: nothing taken off

    def test_an_independent_family_adds_up_through_fisher(self):
        cal = _inf("calendar.free", 0.1, 1.0, family="calendar")
        out = away_unusual.combine("1", "a", _presence(p=0.05, conf=1.0), [], 0, NOW, extra=[cal])

        assert out.probability < 0.05 and out.evidence["method"] == "fisher_by_family"
        assert out.evidence["families"] == ["calendar", "network"]

    def test_quiet_without_an_away_presence_deviation(self):
        home = _inf(presence.SIGNAL, 0.05, 0.4, state="home")

        assert away_unusual.combine("1", "a", None, [_device("7")], 1, NOW) is None
        assert away_unusual.combine("1", "a", home, [], 0, NOW) is None

    def test_below_three_bits_is_quiet(self):
        assert away_unusual.combine("1", "a", _presence(p=0.2), [], 0, NOW) is None

    def test_parents_are_listed_for_the_card(self):
        out = away_unusual.combine("1", "a", _presence(), [_device("7")], 2, NOW)

        assert [p["signal"] for p in out.evidence["parents"]] == [
            presence.SIGNAL,
            device_rhythm.SIGNAL_AVAILABILITY,
        ]
        assert out.evidence["devices_offline"] == 1 and out.evidence["devices_with_profile"] == 2


class TestShadowAway:
    def _runner(self, rows, presence_inf):
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        db = MagicMock()
        db.cursor.return_value = cursor
        persisted = []
        runner = shadow.ShadowRunner(lambda: db, persisted.extend)
        runner.profiles = lambda name: (
            [SimpleNamespace(subject_id="1")] if name == presence.NAME else []
        )
        return runner, persisted

    def _frame(self, home):
        return SimpleNamespace(
            now=datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc),
            local_dt=datetime(2026, 10, 9, 11, 0),
            person_presence=[
                {
                    "user_id": 1,
                    "username": "athos",
                    "user_type": "owner",
                    "home": home,
                    "last_online": datetime(2026, 10, 9, 12, 0),
                }
            ],
        )

    def test_everyone_home_is_quiet_and_touches_nothing(self):
        runner, persisted = self._runner([], None)

        assert runner.away(self._frame(home=True)) == [] and persisted == []

    def test_an_away_person_with_an_improbable_absence_is_combined_and_persisted(self, monkeypatch):
        runner, persisted = self._runner([], None)
        monkeypatch.setattr(
            shadow.presence.PresenceLearner, "score", lambda self, profile, state, now: _presence()
        )

        found = runner.away(self._frame(home=False))

        assert len(found) == 1 and persisted == found and found[0].layer == 2
        assert found[0].subject_id == "1"

    def test_a_weakly_trusted_second_family_never_lowers_the_surprise(self):
        weak = _inf("calendar.free", 0.5, 0.1, family="calendar")
        out = away_unusual.combine("1", "a", _presence(p=0.05, conf=0.4), [], 0, NOW, extra=[weak])

        assert out.probability <= 0.05
