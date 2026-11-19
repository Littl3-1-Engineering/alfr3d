"""Weak witnesses (Context learning 5/5): the layer-2 mechanism, the Deck-location observer and its
use by `away_unusual`. The properties that matter: a witness can only move CONFIDENCE, by a bounded
amount; it can never create or remove a surprise; with no witness, or with witnesses off (the
default), the result is exactly what it was."""

import copy
from datetime import datetime, timedelta

import pytest

from services.service_sa.sa import families, layer2
from services.service_sa.sa.learners import away_unusual, deck_location, presence
from services.service_sa.sa.learners.base import Inference

NOW = datetime(2026, 11, 19, 14, 0)
HOME = (43.6396, -79.5717)
FAR_PLACE = (43.7001, -79.4163)  # about 13 km away
NEAR_PLACE = (43.6401, -79.5722)


def _with(row, **changes):
    clone = copy.copy(row)
    for key, value in changes.items():
        setattr(clone, key, value)
    return clone


def _presence(p=0.01, conf=0.8):
    return Inference(
        kind="deviation",
        subject_type="user",
        subject_id="1",
        signal=presence.SIGNAL,
        learner="presence_profile",
        learner_version="1",
        window_start=NOW - timedelta(hours=2),
        observed={"state": "away", "away_minutes": 120},
        probability=p,
        surprise=0.0,
        confidence=conf,
        evidence={"username": "athos"},
    )


def _fixes(place, minutes_ago=10, n=1):
    return [
        (NOW - timedelta(minutes=minutes_ago + 20 * i), place[0], place[1], 2000.0)
        for i in range(n)
    ]


def _witness(place=FAR_PLACE, minutes_ago=10):
    return deck_location.observe(1, "inst", _fixes(place, minutes_ago), NOW, HOME)


def _rule(enabled):
    rule = away_unusual.AwayUnusualRule()
    rule.witness_families = ("deck_location",) if enabled else ()
    return rule


def _run(rule, parents):
    return layer2.run_rules([rule], parents, {"owners": {}, "owned_with_profile": {}}, NOW)


class TestObserver:
    def test_far_and_near_and_the_ambiguous_middle(self):
        assert _witness(FAR_PLACE).observed["state"] == "far"
        assert _witness(NEAR_PLACE).observed["state"] == "near"
        middle = (43.6396 + 0.03, -79.5717)  # about 3.3 km: between NEAR_KM and FAR_KM
        assert deck_location.observe(1, "i", _fixes(middle), NOW, HOME) is None

    def test_a_stale_fix_a_missing_home_and_no_fixes_are_no_evidence(self):
        assert _witness(FAR_PLACE, minutes_ago=90) is None
        assert deck_location.observe(1, "i", _fixes(FAR_PLACE), NOW, None) is None
        assert deck_location.observe(1, "i", [], NOW, HOME) is None
        future = [(NOW + timedelta(minutes=5), *FAR_PLACE, 2000.0)]
        assert deck_location.observe(1, "i", future, NOW, HOME) is None  # not yet captured

    def test_the_newest_fix_decides(self):
        fixes = [
            (NOW - timedelta(minutes=40), *NEAR_PLACE, 2000.0),
            (NOW - timedelta(minutes=5), *FAR_PLACE, 2000.0),
        ]
        assert deck_location.observe(1, "i", fixes, NOW, HOME).observed["state"] == "far"

    def test_the_row_is_a_state_with_no_probability_in_the_witness_family(self):
        row = _witness()
        assert row.kind == "state" and row.probability is None
        assert layer2.family_of(row) == "deck_location"
        assert families.role_of("deck_location") == families.WITNESS

    def test_modal_home_finds_the_commonest_place(self):
        fixes = [(NOW, *HOME, 2000.0)] * 5 + [(NOW, *FAR_PLACE, 2000.0)] * 2
        assert deck_location.modal_home(fixes) == (round(HOME[0], 3), round(HOME[1], 3))
        assert deck_location.modal_home([]) is None


class TestMechanism:
    def test_a_witness_off_by_default_changes_nothing(self):
        plain = _run(_rule(False), [_presence()])
        offered = _run(_rule(False), [_presence(), _witness(FAR_PLACE)])
        assert plain and offered
        assert offered[0].confidence == plain[0].confidence
        assert "witnesses" not in offered[0].evidence

    def test_far_raises_and_near_lowers_confidence_by_the_family_quality(self):
        base = _run(_rule(True), [_presence()])[0]
        up = _run(_rule(True), [_presence(), _witness(FAR_PLACE)])[0]
        down = _run(_rule(True), [_presence(), _witness(NEAR_PLACE)])[0]
        assert up.confidence > base.confidence > down.confidence
        quality, strength = families.quality_of("deck_location"), deck_location.CONFIDENCE
        shift = min(layer2.WITNESS_CAP, quality * strength)
        assert shift < layer2.WITNESS_CAP  # one witness alone does not hit the cap
        assert up.confidence == pytest.approx(base.confidence * (1 + shift), abs=1e-3)
        assert down.confidence == pytest.approx(base.confidence * (1 - shift), abs=1e-3)
        assert up.evidence["witnesses"][0]["direction"] == "corroborates"
        assert down.evidence["witnesses"][0]["direction"] == "contradicts"

    def test_a_witness_never_changes_the_surprise_or_the_flag(self):
        base = _run(_rule(True), [_presence()])[0]
        for place in (FAR_PLACE, NEAR_PLACE):
            moved = _run(_rule(True), [_presence(), _witness(place)])[0]
            assert (moved.surprise, moved.probability) == (base.surprise, base.probability)

    def test_a_witness_cannot_create_a_surprise_that_the_voters_do_not_show(self):
        weak = _presence(p=0.5)  # one bit: far below the 3-bit bar
        assert _run(_rule(True), [weak]) == []
        assert _run(_rule(True), [weak, _witness(FAR_PLACE)]) == []

    def test_a_witness_cannot_rescue_or_remove_a_result_at_the_bar(self):
        edge = _presence(p=2**-3.2)  # just over 3 bits
        assert _run(_rule(True), [edge, _witness(NEAR_PLACE)])  # still flagged when contradicted
        assert _run(_rule(True), [edge, _witness(FAR_PLACE)])

    def test_the_effect_is_capped(self):
        group = layer2.Group(
            "1", _presence(), [_presence()], witnesses=[(_witness(FAR_PLACE), 1)] * 10
        )
        rule = _rule(True)
        used = layer2.witness_effects(rule, group)
        assert len(used) == 10
        base = layer2.fuse(rule, replace_group(group, []), NOW).confidence
        capped = layer2.fuse(rule, group, NOW).confidence
        assert capped == pytest.approx(base * (1 + layer2.WITNESS_CAP), abs=1e-3)

    def test_a_witness_row_with_no_confidence_says_nothing(self):
        silent = _with(_witness(FAR_PLACE), confidence=None)
        group = layer2.Group("1", _presence(), [_presence()], witnesses=[(silent, 1)])
        assert layer2.witness_effects(_rule(True), group) == []

    def test_a_witness_family_never_votes_even_if_passed_as_a_parent(self):
        row = _with(_witness(FAR_PLACE), probability=1e-9)  # absurdly surprising
        result = _run(_rule(True), [_presence(), row])[0]
        assert "deck_location" not in result.evidence["families"]

    def test_a_rule_only_hears_the_families_it_lists(self):
        other = _rule(True)
        other.witness_families = ("not_deck_location",)
        base = _run(other, [_presence()])[0]
        assert _run(other, [_presence(), _witness(FAR_PLACE)])[0].confidence == base.confidence


def replace_group(group, witnesses):
    return layer2.Group(
        group.subject_id, group.anchor, group.parents, witnesses=witnesses, evidence=group.evidence
    )


# --- the replay pieces that measure the Deck-location witness -----------------------------------

from services.service_sa.sa import replay  # noqa: E402


class TestReplayMeasurement:
    def _locations(self, place=FAR_PLACE, minutes_ago=10):
        fixes = {"inst": [(NOW - timedelta(minutes=minutes_ago), *place, 2000.0)]}
        return fixes, {"inst": 1}, {"inst": HOME}

    def test_the_state_is_what_live_would_have_written_at_that_instant(self):
        far = replay.location_state_at(self._locations(FAR_PLACE), 1, NOW)
        near = replay.location_state_at(self._locations(NEAR_PLACE), 1, NOW)
        assert far.observed["state"] == "far" and near.observed["state"] == "near"

    def test_other_people_a_stale_fix_and_the_future_are_no_evidence(self):
        assert replay.location_state_at(self._locations(), 2, NOW) is None  # another user
        assert replay.location_state_at(self._locations(minutes_ago=120), 1, NOW) is None
        assert replay.location_state_at(self._locations(), 1, NOW - timedelta(hours=1)) is None

    def test_no_fixes_in_the_lake_is_an_empty_replay_not_an_error(self, tmp_path):
        assert replay.load_locations(tmp_path) == ({}, {}, {})

    def test_the_summary_counts_card_flags_the_witness_moved(self):
        # (baseline conf, witnessed conf, place, day, user, reaches card without, with)
        floor = replay.CARD_CONFIDENCE_FLOOR
        pairs = [
            (floor + 0.05, floor - 0.05, "near", "d1", 1, True, False),  # pushed under the bar
            (floor - 0.05, floor + 0.05, "far", "d2", 1, False, True),  # lifted over it
            (0.9, 0.9, "none", "d3", 1, True, True),
        ]
        out = replay._witness_summary(
            {
                "by_location": {"far": 1, "near": 1, "none": 1},
                "agreement": {"far|out": 1},
                "pairs": pairs,
            }
        )
        assert (out["card_flags_removed"], out["card_flags_added"]) == (1, 1)
        assert (out["card_flag_days_removed"], out["card_flag_days_added"]) == (1, 1)
        assert (
            out["confidence_raised"],
            out["confidence_lowered"],
            out["confidence_unchanged"],
        ) == (1, 1, 1)
        assert out["flagged_by_location_state"] == {"far": 1, "near": 1, "none": 1}
        assert out["location_vs_deck_network"] == {"far|out": 1}

    def test_an_empty_summary_has_no_mean(self):
        out = replay._witness_summary(
            {"by_location": {"far": 0, "near": 0, "none": 0}, "agreement": {}, "pairs": []}
        )
        assert out["mean_confidence_change"] is None and out["card_flags_removed"] == 0
