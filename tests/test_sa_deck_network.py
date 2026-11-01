"""Tests for the Deck network observer and how away_unusual uses it (LF-6)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.service_sa.sa import layer2, shadow
from services.service_sa.sa.learners import (
    away_unusual,
    deck_network,
    device_rhythm,
    presence,
)
from services.service_sa.sa.learners.base import Inference

NOW = datetime(2026, 11, 1, 12, 0)


def _reports(kind, count, step=15, end=None, then=None):
    """`count` reports of `kind`, `step` minutes apart, the newest at `end`; `then` prepends older
    reports of another kind: (kind, count)."""
    end = end or NOW
    out = [(end - timedelta(minutes=step * i), kind) for i in range(count)]
    if then:
        oldest = out[-1][0]
        out += [(oldest - timedelta(minutes=step * (i + 1)), then[0]) for i in range(then[1])]
    return out


class TestSustainedState:
    def test_cellular_for_half_an_hour_is_out(self):
        state, since, count = deck_network.sustained_state(_reports("cellular", 3), NOW)

        assert state == deck_network.OUT and count == 3
        assert since == NOW - timedelta(minutes=30)

    def test_wifi_for_half_an_hour_is_wifi(self):
        assert deck_network.sustained_state(_reports("wifi", 3), NOW)[0] == deck_network.WIFI

    def test_a_single_cellular_report_is_noise(self):
        assert deck_network.sustained_state(_reports("cellular", 1), NOW) is None

    def test_a_short_cellular_stretch_is_noise(self):
        assert deck_network.sustained_state(_reports("cellular", 2, step=10), NOW) is None

    def test_a_newer_wifi_report_ends_the_cellular_run(self):
        reports = _reports("cellular", 3, end=NOW - timedelta(minutes=15)) + [(NOW, "wifi")]

        assert deck_network.sustained_state(reports, NOW) is None

    def test_only_the_unbroken_tail_counts(self):
        reports = _reports("cellular", 3, then=("wifi", 5))

        assert deck_network.sustained_state(reports, NOW)[2] == 3

    def test_a_stale_newest_report_is_not_now(self):
        assert (
            deck_network.sustained_state(_reports("cellular", 3), NOW + timedelta(hours=1)) is None
        )

    def test_staleness_follows_the_installs_own_cadence(self):
        later = NOW + timedelta(minutes=45)

        assert deck_network.sustained_state(_reports("cellular", 3), later) is None
        assert (
            deck_network.sustained_state(_reports("cellular", 3), later, gap_minutes=30) is not None
        )

    def test_other_networks_and_nothing_are_no_state(self):
        assert deck_network.sustained_state(_reports("ethernet", 4), NOW) is None
        assert deck_network.sustained_state([], NOW) is None

    def test_cadence_needs_enough_reports_to_measure(self):
        few = [
            NOW - timedelta(minutes=15 * i) for i in range(deck_network.MIN_REPORTS_FOR_CADENCE - 1)
        ]
        many = [NOW - timedelta(minutes=15 * i) for i in range(40)]

        assert deck_network.median_gap_minutes(few) is None
        assert deck_network.median_gap_minutes(many) == 15


def _away_presence(conf=0.4, p=2**-4.5):
    return Inference(
        kind="deviation", subject_type="user", subject_id="1", signal=presence.SIGNAL,
        learner="presence_profile", learner_version="1", window_start=NOW - timedelta(hours=3),
        observed={"state": "away", "away_minutes": 180.0}, expected={"p_home": 0.9},
        probability=p, surprise=4.5, confidence=conf, n_eff=10.0, context={"hour_local": 11},
    )  # fmt: skip


def _device_off(device, conf=0.5):
    return Inference(
        kind="deviation", subject_type="device", subject_id=device,
        signal=device_rhythm.SIGNAL_AVAILABILITY, learner="device_rhythm", learner_version="1",
        window_start=NOW - timedelta(hours=3), observed={"state": "offline"}, probability=0.2,
        surprise=2.3, confidence=conf, n_eff=10.0,
    )  # fmt: skip


def _deck(state, user="1"):
    return deck_network.observe(
        user,
        "f05e8522-927c",
        _reports("cellular" if state == "out" else "wifi", 3),
        NOW,
    )


CTX = {
    "owners": {"7": 1},
    "owned_with_profile": {"1": 4},
}  # one of four owned devices offline


class TestAwayUnusualUsesTheDeck:
    def _run(self, parents):
        return layer2.run_rules([away_unusual.RULE], parents, CTX, NOW)

    def test_no_deck_row_is_exactly_the_old_behaviour(self):
        out = self._run([_away_presence(), _device_off("7")])

        assert abs(out[0].confidence - 0.4 * (0.6 + 0.4 * 0.25)) < 1e-3
        assert out[0].evidence["deck_network"] is None

    def test_sustained_cellular_corroborates_to_full_confidence(self):
        out = self._run([_away_presence(), _device_off("7"), _deck("out")])

        assert out[0].confidence == 0.4 and out[0].evidence["deck_network"] == "out"
        assert (
            abs(out[0].probability - 2**-4.5) < 1e-9
        )  # corroboration moves confidence, not surprise

    def test_cellular_corroborates_a_person_with_no_other_device_evidence(self):
        out = self._run([_away_presence(), _deck("out")])

        assert out[0].confidence == 0.4

    def test_sustained_wifi_explains_the_absence_away(self):
        parents = [_away_presence(), _deck("wifi")]

        assert self._run(parents) == []  # 4.5 bits * 0.3 < the 3-bit bar

    def test_a_big_enough_absence_survives_wifi_but_is_flagged_explained(self):
        out = self._run([_away_presence(p=2**-12), _deck("wifi")])

        assert out and out[0].evidence["explained_by"][0]["signal"] == deck_network.SIGNAL

    def test_arp_alone_still_detects_absence_for_everyone_without_a_deck(self):
        other = _away_presence()
        other.subject_id = "2"
        out = self._run([_away_presence(), other, _deck("out", user="2")])
        by_user = {o.subject_id: o for o in out}

        assert set(by_user) == {
            "1",
            "2",
        }  # the person with no Deck is detected all the same
        assert by_user["1"].evidence["deck_network"] is None
        assert by_user["2"].evidence["deck_network"] == "out"

    def test_another_persons_deck_does_not_vote_for_this_one(self):
        out = self._run([_away_presence(), _deck("wifi", user="2")])

        assert out and out[0].evidence["deck_network"] is None

    def test_the_deck_row_never_votes_by_itself(self):
        assert self._run([_deck("out")]) == []
        assert layer2.family_of(_deck("out")) == "deck"


class TestDeckNetworkState:
    def _runner(self, install_user, gap_rows, recent_rows):
        calls = []
        cursor = MagicMock()

        def execute(sql, params=None):
            calls.append(sql)
            if "FROM device_location_history" in sql:
                cursor.fetchall.return_value = install_user
            elif (
                "observed_at >= %s" in sql
                and "AND observed_at >= %s" in sql
                and params[1] < NOW - timedelta(days=1)
            ):
                cursor.fetchall.return_value = gap_rows
            else:
                cursor.fetchall.return_value = recent_rows

        cursor.execute.side_effect = execute
        db = MagicMock()
        db.cursor.return_value = cursor
        persisted = []
        return shadow.ShadowRunner(lambda: db, persisted.extend), persisted, calls

    def _frame(self):
        return SimpleNamespace(now=NOW.replace(tzinfo=timezone.utc))

    def test_one_reporting_deck_gives_that_person_a_state_row(self):
        runner, persisted, _ = self._runner(
            [("f05e8522-927c", 1)], [(NOW - timedelta(minutes=15 * i),) for i in range(40)],
            _reports("cellular", 3),
        )  # fmt: skip

        rows = runner.deck_network_state(self._frame())

        assert persisted == rows and len(rows) == 1
        assert rows[0].subject_id == "1" and rows[0].observed == {"state": "out"}
        assert rows[0].kind == "state" and rows[0].probability is None

    def test_a_quiet_deck_writes_nothing(self):
        runner, persisted, _ = self._runner([("i", 1)], [], _reports("cellular", 1))

        assert runner.deck_network_state(self._frame()) == [] and persisted == []

    def test_no_known_install_writes_nothing(self):
        runner, persisted, _ = self._runner([], [], [])

        assert runner.deck_network_state(self._frame()) == [] and persisted == []

    def test_install_links_are_cached_for_an_hour(self):
        runner, _, calls = self._runner([("i", 1)], [], _reports("wifi", 1))
        runner.deck_network_state(self._frame())
        first = sum("device_location_history" in c for c in calls)
        runner.deck_network_state(self._frame())

        assert first == 1 and sum("device_location_history" in c for c in calls) == 1
