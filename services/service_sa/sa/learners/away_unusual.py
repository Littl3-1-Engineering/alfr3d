"""Away-unusual (LF-6): a person is out when their usual rhythm says they should be home.

The second LAYER-2 inference. It reads layer-1 rows only, never raw data:

- the person's `presence.home` deviation where the observed state is "away" (the presence
  learner has already required >= 3 bits of surprise and >= 60 minutes away),
- `device.online` deviations (offline when usually on) for devices that person owns,
- optional parents from other source families (calendar, Home Assistant trackers) when a learner
  for them exists. None does yet, so today every parent is in the "network" family.

Combination follows todo/sa/todo_lf6_layer2.md:

- Parents in the same source family are NOT independent evidence (a phone's presence and its
  device-rhythm row are the same arp-scan sightings), so a family counts once, by its most
  surprising parent. Families are then combined with confidence-weighted Fisher, as household_day
  does.
- Several of a person's own devices going quiet together does not make the absence more surprising,
  but it does make it more believable: a lone phone can be off, charging dead or out of wifi range
  while its owner is home. So corroboration scales confidence, not probability:

      confidence = mean family confidence * (CORROBORATION_FLOOR + (1 - FLOOR) * corroborated share)

  where the share is owned devices with a deviation over owned devices that have a rhythm profile.
  Presence alone (no owned device has a profile) keeps the full presence confidence: no evidence
  for or against is not a penalty.
- Parents' confidence already carries their drift stability caps, so a regime change lowers the
  L2 confidence with no extra rule here.

`combine` is a pure function over Inference objects, so a replay needs no database. `replay_day`
runs it over the lake's presence history to check a past day.
"""

import math
from datetime import timedelta

from sa.learners import device_rhythm, presence
from sa.learners.base import Inference
from sa.learners.household_day import fisher_p

NAME = "away_unusual"
VERSION = "1"
SIGNAL = "presence.away_unusual"

MIN_SURPRISE_BITS = 3.0
CORROBORATION_FLOOR = 0.6
FAMILY_NETWORK = "network"
FAMILIES = {presence.SIGNAL: FAMILY_NETWORK, device_rhythm.SIGNAL_AVAILABILITY: FAMILY_NETWORK}


def _family(inference):
    return (inference.evidence or {}).get("family") or FAMILIES.get(inference.signal)


def _is_away(inference):
    return (inference.observed or {}).get("state") in ("away", "offline")


def combine(user_id, username, presence_inf, device_infs, owned_with_profile, now, extra=()):
    """The layer-2 inference for one person, or None.

    presence_inf: that person's presence.home deviation (None if there isn't one);
    device_infs: device.online deviations for devices they own;
    owned_with_profile: how many of their devices have a rhythm profile (the corroboration base);
    extra: further layer-1 deviations from other families (each needs evidence["family"]).
    """
    if presence_inf is None or presence_inf.kind != "deviation" or not _is_away(presence_inf):
        return None
    parents = [presence_inf] + [d for d in device_infs if _is_away(d)] + list(extra)
    families = {}
    for parent in parents:
        family = _family(parent)
        if family is None or parent.probability is None:
            continue
        best = families.get(family)
        if best is None or parent.probability < best.probability:
            families[family] = parent
    voters = list(families.values())
    ps = [max(p.probability, 1e-12) for p in voters]
    cs = [max(p.confidence or 0.0, 1e-6) for p in voters]
    p_comb = ps[0]
    if len(voters) > 1:
        # Weighting by confidence dilutes: a second, weakly trusted family could otherwise make the
        # result LESS surprising than the best family alone. More evidence never lowers surprise.
        p_comb = min(min(ps), max(fisher_p(ps, cs), 1e-12))
    surprise = -math.log2(p_comb)
    if surprise < MIN_SURPRISE_BITS:
        return None
    confidence_mean = sum(cs) / len(cs)
    devices_off = [d for d in device_infs if _is_away(d)]
    share = None
    if owned_with_profile:
        share = min(1.0, len(devices_off) / owned_with_profile)
        confidence_mean *= CORROBORATION_FLOOR + (1.0 - CORROBORATION_FLOOR) * share
    return Inference(
        layer=2,
        kind="deviation",
        subject_type="user",
        subject_id=user_id,
        signal=SIGNAL,
        learner=NAME,
        learner_version=VERSION,
        window_start=presence_inf.window_start,
        window_end=now.replace(microsecond=0),
        context=presence_inf.context,
        observed={
            "state": "away",
            "away_minutes": (presence_inf.observed or {}).get("away_minutes"),
        },
        expected=presence_inf.expected,
        probability=round(p_comb, 12),
        surprise=round(surprise, 3),
        confidence=round(confidence_mean, 4),
        n_eff=presence_inf.n_eff,
        evidence={
            "method": "fisher_by_family" if len(voters) > 1 else "single_family",
            "username": username,
            "families": sorted(families),
            "parents": [
                {
                    "signal": p.signal,
                    "subject_id": p.subject_id,
                    "p": p.probability,
                    "confidence": p.confidence,
                    "family": _family(p),
                }
                for p in parents
            ],
            "devices_offline": len(devices_off),
            "devices_with_profile": owned_with_profile,
            "corroboration": None if share is None else round(share, 3),
        },
        expires_at=now + timedelta(hours=6),
    )


def replay_day(lake_dir, user_id, day, hours=range(6, 23), learner=None):
    """Presence-only replay of one past day: the hourly layer-2 results (None where quiet), each
    hour scored by a presence model fitted on earlier days. Device parents are not replayed (the
    rhythm profiles are per device and the lake has no owner map here), so confidence is the
    presence confidence and corroboration is None."""
    results = presence.backtest(lake_dir, user_id, day, day, learner=learner, hours=hours)
    out = []
    for row in results:
        profile = row["profile"]
        now = row["at_local"]  # only used for stamps in a replay
        inference = combine(
            str(user_id), profile.params.get("username"), row["inference"], [], 0, now
        )
        out.append((row["at_local"], inference))
    return out
