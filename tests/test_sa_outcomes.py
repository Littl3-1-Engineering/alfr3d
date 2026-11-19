"""Outcome labels (sa/outcomes.py): definitions applied to recorded events. Nothing here executes
anything; the tests pin each rule, including the ones that protect the household (a negative
outcome always wins; a change made by a wall switch still counts as acted on)."""

from datetime import date, datetime, timedelta

import pytest

from services.service_sa.sa import outcomes

T0 = datetime(2026, 11, 19, 18, 0)


class TestCardLabels:
    @pytest.mark.parametrize(
        "actions,age,label,basis",
        [
            (["tapped"], 1, "acted_on", "tapped"),
            (["acked"], 1, "acted_on", "acked"),
            (["tapped", "acked"], 1, "acted_on", "tapped"),
            (["dismissed"], 1, "ignored", "dismissed"),
            (["expired"], 30, "ignored", "expired"),
            (["not_useful"], 1, "rejected", "not_useful"),
            ([], 1, "pending", "no outcome yet"),
            ([], 30, "ignored", "no outcome within the TTL"),
        ],
    )
    def test_each_outcome(self, actions, age, label, basis):
        assert outcomes.label_card(actions, age) == (label, basis)

    def test_a_negative_outcome_always_wins(self):
        # a demotion must never be missed, whatever else happened to the card
        assert outcomes.label_card(["tapped", "acked", "not_useful"], 2)[0] == "rejected"
        assert outcomes.label_card(["dismissed", "not_useful"], 2)[0] == "rejected"

    def test_a_positive_beats_a_neutral_dismissal(self):
        assert outcomes.label_card(["dismissed", "acked"], 2)[0] == "acted_on"

    def test_unknown_actions_are_not_an_outcome(self):
        assert outcomes.label_card(["shown", "impression"], 2)[0] == "pending"


def _on(minutes):
    return [(T0 + timedelta(minutes=minutes), "on")]


class TestActionLabels:
    NOW = T0 + timedelta(hours=3)

    def test_acted_on_by_the_household_whoever_flipped_it(self):
        label, cause, _ = outcomes.label_action("switch_on", T0, "on", _on(12), self.NOW)
        assert (label, cause) == ("acted_on", "household")  # e.g. a wall switch, no API command

    def test_the_change_must_be_the_predicted_one_inside_the_window(self):
        wrong_way = [(T0 + timedelta(minutes=5), "off")]
        assert outcomes.label_action("switch_on", T0, "on", wrong_way, self.NOW)[0] == "ignored"
        late = _on(90)  # window is 60 minutes
        assert outcomes.label_action("switch_on", T0, "on", late, self.NOW)[0] == "ignored"
        before = [(T0 - timedelta(minutes=5), "on")]  # already on before the proposal
        assert outcomes.label_action("switch_on", T0, "on", before, self.NOW)[0] == "ignored"

    def test_pending_while_the_window_is_open_then_ignored(self):
        soon = T0 + timedelta(minutes=20)
        assert outcomes.label_action("switch_on", T0, "on", [], soon)[0] == "pending"
        assert outcomes.label_action("switch_on", T0, "on", [], self.NOW)[0] == "ignored"

    def test_an_explicit_decline_is_rejected_even_if_the_change_happened(self):
        got = outcomes.label_action("switch_on", T0, "on", _on(5), self.NOW, declined=True)
        assert got[0] == "rejected"

    def test_an_alfr3d_action_reversed_by_a_person_in_time_is_undone(self):
        reverted = T0 + timedelta(minutes=20)
        label, cause, _ = outcomes.label_action(
            "switch_on",
            T0,
            "on",
            _on(1),
            self.NOW,
            performed_by="alfr3d",
            reverted_by_person=reverted,
        )
        assert (label, cause) == ("undone", "alfr3d")

    def test_a_reversal_too_late_or_of_a_household_change_is_not_an_undo(self):
        late = T0 + timedelta(hours=2)
        got = outcomes.label_action(
            "switch_on", T0, "on", _on(1), self.NOW, performed_by="alfr3d", reverted_by_person=late
        )
        assert got[0] == "acted_on"  # the household turning it off much later is not an undo
        mine = outcomes.label_action(
            "switch_on", T0, "on", _on(1), self.NOW, reverted_by_person=T0 + timedelta(minutes=10)
        )
        assert mine[0] == "acted_on"  # an undo only exists for an action Alfr3d performed

    def test_a_new_action_type_inherits_the_labelling_by_registration(self, monkeypatch):
        monkeypatch.setitem(
            outcomes.ACTION_TYPES, "blind_down", outcomes.ActionType("blind_down", 10, 5)
        )
        assert (
            outcomes.label_action(
                "blind_down", T0, "down", [(T0 + timedelta(minutes=3), "down")], self.NOW
            )[0]
            == "acted_on"
        )
        assert (
            outcomes.label_action(
                "blind_down", T0, "down", [(T0 + timedelta(minutes=30), "down")], self.NOW
            )[0]
            == "ignored"
        )


def _row(rule, action, imp, at, user=1, surface="deck"):
    return (rule, action, imp, at, user, surface)


class TestCardReport:
    NOW = datetime(2026, 11, 19, 12, 0)
    START, END = date(2026, 11, 1), date(2026, 11, 18)

    def _rows(self):
        d = datetime(2026, 11, 10, 9, 0)
        return [
            _row("household_composition", "impression", "a", d),
            _row("household_composition", "tapped", "a", d + timedelta(minutes=1)),
            _row("household_composition", "impression", "b", d),
            _row("rhythm_break_anomaly", "impression", "c", d),
            _row("rhythm_break_anomaly", "dismissed", "c", d + timedelta(minutes=2)),
            _row("rhythm_break_anomaly", "impression", "d", d),
            _row("rhythm_break_anomaly", "not_useful", "d", d + timedelta(minutes=3)),
            _row("time", "impression", "e", datetime(2026, 11, 18, 23, 0)),  # inside the TTL
            _row("time", "shown", None, d),  # the loop's own log: not a card
            _row("time", "dismissed", None, d),  # an old outcome with no impression id
            _row("time", "impression", "z", datetime(2026, 10, 1)),  # outside the window
        ]

    def test_counts_per_rule_with_each_label(self):
        out = outcomes.card_report(self._rows(), self.START, self.END, now=self.NOW)
        assert out["impressions"] == 5
        hc = out["per_rule"]["household_composition"]
        assert (hc["acted_on"], hc["ignored"], hc["total"]) == (1, 1, 2)  # b aged past the TTL
        rb = out["per_rule"]["rhythm_break_anomaly"]
        assert (rb["ignored"], rb["rejected"]) == (1, 1)
        assert out["per_rule"]["time"]["pending"] == 1

    def test_an_outcome_without_an_impression_id_is_counted_apart_never_guessed(self):
        out = outcomes.card_report(self._rows(), self.START, self.END, now=self.NOW)
        assert out["explicit_outcomes_without_an_impression_id"] == {"time:dismissed": 1}

    def test_the_window_excludes_other_impressions(self):
        out = outcomes.card_report(self._rows(), self.START, self.END, now=self.NOW)
        assert "z" not in str(out) and out["window"] == ["2026-11-01", "2026-11-18"]

    def test_no_lake_is_an_empty_report(self, tmp_path):
        assert outcomes.load_cards(tmp_path) == []
        out = outcomes.card_report([], self.START, self.END, now=self.NOW)
        assert out["impressions"] == 0 and out["per_rule"] == {}
