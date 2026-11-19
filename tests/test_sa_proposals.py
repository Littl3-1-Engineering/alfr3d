"""The layer-3 proposal contract and autonomy policy (sa/proposals.py). The acceptance test of the
phase lives here: nothing at level 0 can execute a device command, because this module cannot reach
a device at all and a level-0 decision can only ever be a card. The rest pins the rules the owner
set: default level 0, owner-only promotion shown with its evidence, automatic demotion, guests
never, household scope only, no never-list."""

import inspect
from datetime import datetime

import pytest

from services.service_sa.sa import outcomes, proposals

NOW = datetime(2026, 11, 19, 20, 0)
KNOWN = tuple(outcomes.ACTION_TYPES)
EVIDENCE = {"proposals": 24, "acted_on": 21, "undone": 0, "rejected": 1}
KEY = ("switch_on", proposals.HOUSEHOLD, "", proposals.DEFAULT_CONTEXT)


def _proposal(**changes):
    base = dict(
        action_type="switch_on",
        subject="switch.living_room_lamp",
        target_state="on",
        because=["on in 14 of 17 comparable weekday hours at 19:00"],
        probability=0.9,
        confidence=0.6,
        cost_of_being_wrong="trivial",
        reversibility="undoable",
        predictor="switch_usual_state",
    )
    base.update(changes)
    return proposals.Proposal(**base)


def _granted(level, context=proposals.DEFAULT_CONTEXT):
    policy = proposals.Policy()
    for to in range(1, level + 1):
        policy.promote(
            ("switch_on", proposals.HOUSEHOLD, "", context), to, "athos", "owner", EVIDENCE, NOW
        )
    return policy


class TestNothingAtLevelZeroExecutes:
    def test_level_zero_can_only_ever_be_a_card(self):
        policy = proposals.Policy()
        for cost in proposals.COSTS:
            for reversibility in proposals.REVERSIBILITY:
                got = proposals.decide(
                    _proposal(cost_of_being_wrong=cost, reversibility=reversibility), policy, KNOWN
                )
                assert got["mode"] == "card" and got["level"] == 0 and not got["blocked"]

    def test_an_action_type_nobody_registered_is_blocked_not_run(self):
        got = proposals.decide(_proposal(action_type="open_garage"), proposals.Policy(), KNOWN)
        assert got["blocked"] and got["mode"] is None

    def test_the_module_cannot_reach_a_device_or_a_network(self):
        source = inspect.getsource(proposals)
        for forbidden in (
            "device_control",
            "control_iot_device",
            "get_producer",
            "requests",
            "pymysql",
            "subprocess",
            "def execute",
            "def run_command",
        ):
            assert forbidden not in source
        assert not any(name.startswith(("execute", "run_command")) for name in dir(proposals))

    def test_decide_returns_data_it_does_not_act_at_any_level(self):
        for level in proposals.LEVELS:
            got = proposals.decide(_proposal(), _granted(level), KNOWN)
            assert set(got) == {"mode", "level", "blocked", "why"}  # a description, nothing else

    def test_a_killed_policy_is_back_to_cards_only(self):
        policy = _granted(3)
        assert proposals.decide(_proposal(), policy, KNOWN)["mode"] == "act_then_tell"
        policy.kill("athos", NOW)
        assert proposals.decide(_proposal(), policy, KNOWN)["mode"] == "card"


class TestDefaults:
    def test_a_missing_row_is_level_zero(self):
        assert proposals.Policy().level("switch_on") == 0
        assert proposals.Policy().level("anything_unregistered") == 0

    def test_starting_rows_are_level_zero_data_over_the_registry(self):
        rows = proposals.starting_rows(KNOWN)
        assert {r.action_type for r in rows} == set(KNOWN) and {r.level for r in rows} == {0}
        source = inspect.getsource(proposals)
        assert "switch_on" not in source and "switch_off" not in source  # not hard-coded here

    def test_a_grant_for_one_context_does_not_leak_into_another(self):
        policy = _granted(2, context="evening")
        assert policy.level("switch_on", context="evening") == 2
        assert policy.level("switch_on", context="morning") == 0
        assert policy.level("switch_on") == 0


class TestPromotion:
    def test_only_the_owner_promotes_and_guests_never(self):
        policy = proposals.Policy()
        for role in ("guest", "resident", "technoking", "", None):
            with pytest.raises(PermissionError):
                policy.promote(KEY, 1, "someone", role, EVIDENCE, NOW)
        assert policy.level("switch_on") == 0 and policy.log == []

    def test_promotion_needs_the_evidence_the_owner_was_shown(self):
        with pytest.raises(ValueError, match="evidence"):
            proposals.Policy().promote(KEY, 1, "athos", "owner", {}, NOW)

    def test_one_level_at_a_time_up_to_three(self):
        policy = proposals.Policy()
        with pytest.raises(ValueError, match="one level"):
            policy.promote(KEY, 2, "athos", "owner", EVIDENCE, NOW)
        for to in (1, 2, 3):
            assert policy.promote(KEY, to, "athos", "owner", EVIDENCE, NOW).level == to
        with pytest.raises(ValueError, match="one level"):
            policy.promote(KEY, 4, "athos", "owner", EVIDENCE, NOW)

    def test_a_promotion_records_who_when_and_what_was_shown(self):
        policy = proposals.Policy()
        row = policy.promote(KEY, 1, "athos", "owner", EVIDENCE, NOW)
        assert (row.granted_by, row.granted_at, row.evidence) == ("athos", NOW, EVIDENCE)
        assert (
            policy.log[-1]["reason"] == "owner promotion" and policy.log[-1]["evidence"] == EVIDENCE
        )

    def test_the_system_can_recommend_but_never_promotes(self):
        assert proposals.recommend(EVIDENCE)["recommend"] is True
        policy = proposals.Policy()
        proposals.recommend(EVIDENCE)
        assert policy.level("switch_on") == 0 and policy.log == []

    @pytest.mark.parametrize(
        "evidence,why",
        [
            ({"proposals": 5, "acted_on": 5}, "only 5 proposals"),
            ({"proposals": 30, "acted_on": 10}, "acceptance"),
            ({"proposals": 30, "acted_on": 28, "undone": 4}, "undo rate"),
        ],
    )
    def test_a_recommendation_says_why_not(self, evidence, why):
        got = proposals.recommend(evidence)
        assert got["recommend"] is False and why in got["reason"]


class TestDemotion:
    def test_an_undo_or_not_useful_drops_one_level_immediately(self):
        policy = _granted(3)
        policy.demote(KEY, "undo", NOW)
        assert policy.level("switch_on") == 2
        policy.demote(KEY, "not useful", NOW)
        assert policy.level("switch_on") == 1
        assert [e["actor"] for e in policy.log[-2:]] == ["system", "system"]

    def test_a_failed_or_ambiguous_undo_goes_straight_to_zero(self):
        policy = _granted(3)
        policy.demote(KEY, "undo failed", NOW, failed_undo=True)
        assert policy.level("switch_on") == 0

    def test_demoting_a_missing_or_zero_row_changes_nothing(self):
        policy = proposals.Policy()
        assert policy.demote(KEY, "undo", NOW) is None and policy.log == []

    def test_only_the_owner_resets_the_kill_switch_and_it_promotes_nothing(self):
        policy = _granted(2)
        policy.kill("athos", NOW)
        assert policy.level("switch_on") == 0
        with pytest.raises(PermissionError):
            policy.reset("guest-1", "guest", NOW)
        policy.reset("athos", "owner", NOW)
        assert policy.level("switch_on") == 2  # as it was; the reset promoted nothing new


class TestGuestsAndScope:
    def test_an_action_is_never_triggered_from_a_guests_pattern(self):
        policy = _granted(3)
        got = proposals.decide(
            _proposal(triggered_by={"person_id": 9, "role": "guest"}), policy, KNOWN
        )
        assert got["blocked"] and "guest" in got["why"]
        resident = proposals.decide(
            _proposal(triggered_by={"person_id": 2, "role": "resident"}), policy, KNOWN
        )
        assert not resident["blocked"]

    def test_only_household_scope_is_built(self):
        assert proposals.validate_row(proposals.PolicyRow("switch_on")) == []
        for scope in (proposals.PERSON, proposals.PRESENCE):
            problems = proposals.validate_row(proposals.PolicyRow("switch_on", scope=scope))
            assert any("not built" in p for p in problems)
        assert proposals.validate_row(proposals.PolicyRow("switch_on", scope="galaxy"))

    def test_a_level_above_zero_needs_a_grant_with_evidence(self):
        bare = proposals.PolicyRow("switch_on", level=2)
        assert any("evidence" in p for p in proposals.validate_row(bare))

    def test_the_person_scope_is_refused_even_by_the_owner(self):
        key = ("switch_on", proposals.PERSON, "2", proposals.DEFAULT_CONTEXT)
        with pytest.raises(ValueError, match="not built"):
            proposals.Policy().promote(key, 1, "athos", "owner", EVIDENCE, NOW)


class TestProposalValidation:
    def test_a_well_formed_proposal_passes(self):
        assert proposals.validate_proposal(_proposal(), KNOWN) == []

    @pytest.mark.parametrize(
        "changes,expect",
        [
            ({"because": []}, "say why"),
            ({"probability": 1.4}, "probability"),
            ({"confidence": None}, "confidence"),
            ({"cost_of_being_wrong": "who knows"}, "cost_of_being_wrong"),
            ({"reversibility": "maybe"}, "reversibility"),
            ({"subject": ""}, "subject"),
            ({"action_type": "x"}, "unknown action type"),
        ],
    )
    def test_each_missing_piece_is_named(self, changes, expect):
        problems = proposals.validate_proposal(_proposal(**changes), KNOWN)
        assert any(expect in p for p in problems)

    def test_no_never_list_every_registered_type_can_be_proposed_and_can_earn_a_level(self):
        # irreversible and serious are allowed to be proposed: the friction is information
        risky = _proposal(cost_of_being_wrong="serious", reversibility="irreversible")
        assert proposals.validate_proposal(risky, KNOWN) == []
        assert proposals.decide(risky, proposals.Policy(), KNOWN)["mode"] == "card"
        assert proposals.decide(risky, _granted(2), KNOWN)["mode"] == "standing"
