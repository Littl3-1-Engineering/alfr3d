"""Layer-2 source families (Context learning 5/5, todo/sa/todo_lf11_families_witnesses.md).

Layer 2 treats parents in one source family as one piece of evidence (a phone's presence and its
device rhythm are the same arp sightings), so a family votes once, by its most surprising parent.
Which family a layer-1 inference belongs to used to be a dict and a prefix tuple inside layer2.py;
a new sensor meant editing that code. It is now declared here, once:

    Family(name, signals, key_prefixes, role, quality, description)

A new sensor joins fusion by one `Family(...)` in `REGISTRY` plus a validation run, with no change
to `layer2.py`. `layer2.family_of` asks this module. A learner can still override per inference by
putting `evidence["family"]`, and an inference with no family is skipped, never silently counted as
independent evidence.

A family has one of two roles:

- `VOTER` (the default, every family before Phase 5): its parents carry a probability and vote in
  the Fisher combination, once per family.
- `WITNESS`: weak or indirect evidence that can never create a surprise and never votes. It can
  only raise or lower the *confidence* of a surprise that voting families already show, by a bounded
  amount scaled by its `quality` (see `layer2.fuse`). A witness with nothing to say changes nothing.

A signal or key prefix belongs to exactly one family, and no prefix may shadow another family's
(`validate`), so the mapping cannot depend on registration order by accident.
"""

from dataclasses import dataclass

VOTER, WITNESS = "voter", "witness"
ROLES = (VOTER, WITNESS)

CALENDAR_BUSY = "calendar.busy"  # layer2.SIGNAL_CALENDAR_BUSY is this same string (tested)


@dataclass(frozen=True)
class Family:
    name: str
    signals: tuple = ()  # exact layer-1 signal names
    key_prefixes: tuple = ()  # series/stream key prefixes (evidence["series"] or ["stream"])
    role: str = VOTER
    quality: float = 1.0  # a witness's weight in (0, 1]; ignored for voters
    description: str = ""


REGISTRY = (
    Family(
        "network",
        signals=("presence.home", "device.online", "device.session_minutes", "presence.daytime"),
        description="Wi-Fi sightings of a person's phone and devices (arp scan).",
    ),
    Family(
        "calendar",
        signals=(CALENDAR_BUSY,),
        description="The household calendar; explains an absence rather than voting on it.",
    ),
    Family(
        "deck",
        signals=("deck.network",),
        description="The phone's own network type, reported by the Deck.",
    ),
    Family("climate", key_prefixes=("esphome:",), description="ESPHome indoor sensors."),
    Family("ha", key_prefixes=("ha:",), description="Home Assistant entities."),
    Family("attention", key_prefixes=("attention:",), description="Deck attention telemetry."),
    Family("email", key_prefixes=("email",), description="Email traffic."),
    Family("events", key_prefixes=("event:",), description="Household event-rate streams."),
    Family(
        "deck_location",
        signals=("deck.location",),
        role=WITNESS,
        quality=0.3,
        description="The phone's coarse (about 2 km) location: near home or clearly elsewhere.",
    ),
)


def validate(registry=None):
    """Problems with a family registry, as strings (empty when it is sound)."""
    problems, names, signals, prefixes = [], set(), {}, []
    for fam in _reg(registry):
        if not fam.name:
            problems.append("a family has no name")
        if fam.name in names:
            problems.append(f"duplicate family name {fam.name!r}")
        names.add(fam.name)
        if fam.role not in ROLES:
            problems.append(f"{fam.name}: unknown role {fam.role!r}")
        if fam.role == WITNESS and not 0.0 < fam.quality <= 1.0:
            problems.append(f"{fam.name}: a witness's quality must be in (0, 1], not {fam.quality}")
        if not fam.signals and not fam.key_prefixes:
            problems.append(f"{fam.name}: claims no signal and no key prefix")
        for signal in fam.signals:
            if signal in signals:
                problems.append(f"signal {signal!r} claimed by {signals[signal]} and {fam.name}")
            signals[signal] = fam.name
        for prefix in fam.key_prefixes:
            if not prefix:
                problems.append(f"{fam.name}: an empty key prefix matches everything")
            for other_prefix, other in prefixes:
                if prefix == other_prefix and other != fam.name:
                    problems.append(f"prefix {prefix!r} claimed by {other} and {fam.name}")
                elif other != fam.name and (
                    prefix.startswith(other_prefix) or other_prefix.startswith(prefix)
                ):
                    problems.append(
                        f"prefix {prefix!r} ({fam.name}) overlaps {other_prefix!r} ({other})"
                    )
            prefixes.append((prefix, fam.name))
    return problems


def _reg(registry):
    return REGISTRY if registry is None else registry


def signal_map(registry=None):
    """{signal: family name}, the shape layer2.FAMILY_BY_SIGNAL always had."""
    return {s: f.name for f in _reg(registry) for s in f.signals}


def prefix_map(registry=None):
    """((prefix, family name), ...) in registration order, the shape FAMILY_BY_KEY_PREFIX had."""
    return tuple((p, f.name) for f in _reg(registry) for p in f.key_prefixes)


def family_for(signal, key="", registry=None):
    """The family name for a signal (exact) or, failing that, a series/stream key (prefix), or
    None. The same lookup layer 2 always did, from the registry."""
    registry = _reg(registry)
    for fam in registry:
        if signal in fam.signals:
            return fam.name
    for fam in registry:
        for prefix in fam.key_prefixes:
            if key.startswith(prefix):
                return fam.name
    return None


def get(name, registry=None):
    return next((f for f in _reg(registry) if f.name == name), None)


def role_of(name, registry=None):
    """VOTER or WITNESS; an unknown (or evidence-overridden) family name is a voter, as before."""
    fam = get(name, registry)
    return fam.role if fam else VOTER


def quality_of(name, registry=None):
    fam = get(name, registry)
    return fam.quality if fam else 1.0
