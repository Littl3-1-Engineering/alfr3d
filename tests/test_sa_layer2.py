"""Tests for the generic layer-2 combiner (sa/layer2.py, LF-6)."""

from datetime import datetime, timedelta

from services.service_sa.sa import layer2
from services.service_sa.sa.learners.base import Inference

NOW = datetime(2026, 10, 12, 12, 0)


def _inf(signal, p, conf, subject="1", evidence=None, state="high"):
    return Inference(
        kind="deviation",
        subject_type="series",
        subject_id=subject,
        signal=signal,
        learner="x",
        learner_version="1",
        window_start=NOW - timedelta(hours=1),
        observed={"state": state},
        probability=p,
        surprise=0.0,
        confidence=conf,
        evidence=evidence or {},
        context={"hour_local": 8},
    )


class HouseRule(layer2.Rule):
    """A toy rule over non-presence signals: one group for the whole household."""

    name = "toy_house"
    signal = "house.toy"
    subject_type = "household"

    def groups(self, parents, ctx):
        mine = [p for p in parents if layer2.family_of(p)]
        return [layer2.Group("house", mine[0], mine)] if mine else []


class TestFamilies:
    def test_known_signals_and_series_keys_map_to_families(self):
        assert layer2.family_of(_inf("presence.home", 0.1, 1)) == "network"
        assert layer2.family_of(_inf("scalar.value", 0.1, 1, evidence={"series": "esphome:x"})) == (
            "climate"
        )
        assert layer2.family_of(_inf("rate.count", 0.1, 1, evidence={"stream": "event:a/b/c"})) == (
            "events"
        )

    def test_an_explicit_family_wins_and_unknown_is_none(self):
        assert layer2.family_of(_inf("presence.home", 0.1, 1, evidence={"family": "ha"})) == "ha"
        assert layer2.family_of(_inf("mystery", 0.1, 1)) is None


class TestFuse:
    def test_two_independent_families_combine_through_fisher(self):
        parents = [
            _inf("scalar.value", 0.01, 0.8, evidence={"series": "esphome:t"}),
            _inf("scalar.value", 0.02, 0.8, subject="2", evidence={"series": "attention:u"}),
        ]
        out = layer2.run_rules([HouseRule()], parents, {}, NOW)

        assert len(out) == 1 and out[0].layer == 2 and out[0].signal == "house.toy"
        assert out[0].probability < 0.01
        assert out[0].evidence["families"] == ["attention", "climate"]
        assert out[0].evidence["method"] == "fisher_by_family"

    def test_one_family_counts_once_by_its_most_surprising_parent(self):
        parents = [
            _inf("scalar.value", 0.02, 0.8, subject="1", evidence={"series": "esphome:t"}),
            _inf("scalar.value", 0.01, 0.8, subject="2", evidence={"series": "esphome:h"}),
        ]
        out = layer2.run_rules([HouseRule()], parents, {}, NOW)

        assert out[0].probability == 0.01 and out[0].evidence["method"] == "single_family"

    def test_below_the_rules_bar_is_quiet_and_unknown_families_do_not_vote(self):
        weak = _inf("scalar.value", 0.5, 0.8, evidence={"series": "esphome:t"})
        mystery = _inf("mystery", 1e-9, 1.0)
        assert layer2.run_rules([HouseRule()], [weak], {}, NOW) == []
        assert layer2.fuse(HouseRule(), layer2.Group("h", mystery, [mystery]), NOW) is None

    def test_parent_refs_carry_the_row_id(self):
        parent = _inf("scalar.value", 0.01, 0.8, evidence={"series": "esphome:t"})
        parent.row_id = 42

        out = layer2.run_rules([HouseRule()], [parent], {}, NOW)

        assert out[0].evidence["parents"][0]["id"] == 42


class TestExplainedBy:
    def _busy(self):
        return _inf(layer2.SIGNAL_CALENDAR_BUSY, None, 1.0, subject="calendar", state="busy")

    def test_an_explanation_discounts_the_surprise_instead_of_voting(self):
        parent = _inf("scalar.value", 2**-10, 0.8, evidence={"series": "esphome:t"})
        group = layer2.Group("h", parent, [parent], explained_by=[self._busy()])

        out = layer2.fuse(HouseRule(), group, NOW)

        assert abs(out.surprise - 10 * 0.3) < 0.01  # default discount 0.7
        assert out.evidence["explained_by"][0]["signal"] == layer2.SIGNAL_CALENDAR_BUSY

    def test_a_discounted_result_below_the_bar_is_quiet(self):
        parent = _inf("scalar.value", 2**-5, 0.8, evidence={"series": "esphome:t"})
        group = layer2.Group("h", parent, [parent], explained_by=[self._busy()])

        assert layer2.fuse(HouseRule(), group, NOW) is None

    def test_the_calendar_row_has_the_calendar_family_and_no_probability(self):
        busy = self._busy()

        assert layer2.family_of(busy) == "calendar" and busy.probability is None
