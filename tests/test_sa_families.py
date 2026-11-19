"""The layer-2 family registry (sa/families.py): the mapping that used to be a dict and a prefix
tuple in layer2.py. The refactor must change nothing (a verbatim copy of the old mapping and the
old lookup are the reference), and a new sensor must join fusion by one registration."""

import random
from dataclasses import replace
from datetime import datetime

from services.service_sa.sa import families, layer2
from services.service_sa.sa.learners.base import Inference

# --- the old mapping and lookup, copied verbatim from layer2.py before the refactor ---------------

OLD_BY_SIGNAL = {
    "presence.home": "network",
    "device.online": "network",
    "device.session_minutes": "network",
    "presence.daytime": "network",
    "calendar.busy": "calendar",
    "deck.network": "deck",
}
OLD_BY_PREFIX = (
    ("esphome:", "climate"),
    ("ha:", "ha"),
    ("attention:", "attention"),
    ("email", "email"),
    ("event:", "events"),
)


def old_family_of(signal, evidence):
    evidence = evidence or {}
    if evidence.get("family"):
        return evidence["family"]
    if signal in OLD_BY_SIGNAL:
        return OLD_BY_SIGNAL[signal]
    key = evidence.get("series") or evidence.get("stream") or ""
    for prefix, family in OLD_BY_PREFIX:
        if key.startswith(prefix):
            return family
    return None


def _inf(signal, evidence=None):
    return Inference(
        kind="deviation",
        subject_type="user",
        subject_id="1",
        signal=signal,
        learner="x",
        learner_version="1",
        window_start=datetime(2026, 11, 19, 12),
        evidence=evidence or {},
    )


class TestParityWithTheOldMapping:
    def test_the_registry_is_sound(self):
        assert families.validate() == []

    def test_the_derived_maps_are_exactly_the_old_literals(self):
        assert layer2.FAMILY_BY_SIGNAL == OLD_BY_SIGNAL
        assert layer2.FAMILY_BY_KEY_PREFIX == OLD_BY_PREFIX
        assert layer2.SIGNAL_CALENDAR_BUSY == families.CALENDAR_BUSY

    def test_every_known_signal_and_prefix_resolves_as_before(self):
        for signal in list(OLD_BY_SIGNAL) + ["scalar.value", "rate.count", "mystery", ""]:
            for key in ("", "esphome:n:T", "ha:light.x", "attention:unlock", "email/all",
                        "event:a/b/c", "other:thing", "esphome", "emai"):  # fmt: skip
                for field in ("series", "stream"):
                    ev = {field: key} if key else None
                    assert layer2.family_of(_inf(signal, ev)) == old_family_of(signal, ev), (
                        signal,
                        key,
                    )

    def test_an_evidence_override_still_wins(self):
        assert layer2.family_of(_inf("presence.home", {"family": "ha"})) == "ha"
        assert layer2.family_of(_inf("mystery")) is None

    def test_fuzzed_inputs_agree_with_the_old_lookup(self):
        rng = random.Random(7)
        pieces = ["esphome:", "ha:", "attention:", "email", "event:", "x", "e", "em", ":", "/"]
        signals = list(OLD_BY_SIGNAL) + ["scalar.value", "rate.count", "mystery"]
        for _ in range(2000):
            key = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 4)))
            signal = rng.choice(signals)
            ev = rng.choice([None, {"series": key}, {"stream": key}, {"family": "zz"}, {}])
            assert layer2.family_of(_inf(signal, ev)) == old_family_of(signal, ev)

    def test_every_family_before_phase_5_is_a_voter(self):
        assert {f.role for f in families.REGISTRY} == {families.VOTER}
        assert families.role_of("network") == families.VOTER
        assert families.role_of("not-a-family") == families.VOTER  # an override name votes


class TestANewSensorJoinsByOneRegistration:
    def test_a_throwaway_family_needs_no_layer2_change(self, monkeypatch):
        fam = families.Family("tuya", key_prefixes=("tuya:",), description="a test sensor")
        monkeypatch.setattr(layer2.families, "REGISTRY", layer2.families.REGISTRY + (fam,))
        parent = _inf("scalar.value", {"series": "tuya:plug:power"})
        assert layer2.family_of(parent) == "tuya"
        assert layer2.families.validate() == []

    def test_a_series_nobody_registered_is_skipped_not_counted(self):
        assert layer2.family_of(_inf("scalar.value", {"series": "tuya:plug:power"})) is None


def _fam(**kw):
    base = dict(name="x", signals=("x.signal",))
    base.update(kw)
    return families.Family(**base)


class TestValidateRejects:
    def test_duplicate_names_and_claims(self):
        assert any(
            "duplicate family name" in p
            for p in families.validate([_fam(), _fam(signals=("y.signal",))])
        )
        assert any(
            "claimed by" in p for p in families.validate([_fam(), _fam(name="y")])
        )  # the same signal twice

    def test_an_empty_family_and_an_empty_prefix(self):
        assert any("claims no signal" in p for p in families.validate([_fam(signals=())]))
        assert any(
            "matches everything" in p
            for p in families.validate([_fam(signals=(), key_prefixes=("",))])
        )

    def test_a_prefix_that_shadows_another_familys(self):
        problems = families.validate(
            [
                _fam(signals=(), key_prefixes=("ha:",)),
                _fam(name="y", signals=(), key_prefixes=("ha:light",)),
            ]
        )
        assert any("overlaps" in p for p in problems)
        assert any(
            "claimed by" in p
            for p in families.validate(
                [
                    _fam(signals=(), key_prefixes=("ha:",)),
                    _fam(name="y", signals=(), key_prefixes=("ha:",)),
                ]
            )
        )

    def test_roles_and_witness_quality(self):
        assert any("unknown role" in p for p in families.validate([_fam(role="oracle")]))
        for quality in (0.0, -0.2, 1.5):
            assert any(
                "quality" in p
                for p in families.validate([_fam(role=families.WITNESS, quality=quality)])
            )
        assert families.validate([_fam(role=families.WITNESS, quality=0.3)]) == []

    def test_a_family_may_repeat_its_own_prefix_shape(self):
        ok = _fam(signals=(), key_prefixes=("ha:", "ha:extra"))  # same family: not shadowing
        assert families.validate([ok]) == []
        assert replace(ok).name == "x"
