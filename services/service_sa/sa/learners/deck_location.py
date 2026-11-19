"""Deck coarse-location observer (Context learning 5/5, todo/sa/todo_lf11_families_witnesses.md): a
weak WITNESS to a person's absence.

The Deck reports a coarse (about 2 km, `accuracy_m` 2000) location fix when the launcher comes to
the foreground, at most once per ten minutes, only with the owner's opt-in
(`device_location_history`).
At 2 km it can separate "near home" from "clearly elsewhere" and nothing finer, so this observer
writes a layer-1 STATE row, never a probability:

- `far`: the newest fix is at least FAR_KM from home, so the phone is clearly elsewhere,
- `near`: the newest fix is within NEAR_KM of home (the fix's own uncertainty),
- nothing: a fix between the two is ambiguous, a stale one is no evidence, and a person with no
  location fixes has no row. Absence of the row is "no evidence", never evidence.

Layer 2 reads it as a witness (sa/families.py family `deck_location`, role WITNESS): far
corroborates an absence, near contradicts it, each only able to move the result's confidence by a
bounded amount.
It is off unless a rule lists `deck_location` in `witness_families`; the Phase 5 measurement decides
whether any rule does (todo_lf11). Precise location is deliberately not used.

`observe` is a pure function over fixes, so a replay needs no database.
"""

import math
from datetime import timedelta

from sa.learners.base import Inference

NAME = "deck_location_observer"
VERSION = "1"
SIGNAL = "deck.location"
FAMILY = "deck_location"

FAR, NEAR = "far", "near"
FAR_KM = 5.0  # well beyond the 2 km fix uncertainty
NEAR_KM = 2.0  # inside the fix's own uncertainty
# Fixes arrive only while the launcher is in the foreground, so a gap is normal. The newest fix must
# be at most this old to count as "now".
STALE_MINUTES = 45
# A witness is weak by construction; this is the row's own confidence (the family quality scales it
# again in layer 2).
CONFIDENCE = 0.4


def distance_km(a, b):
    """Great-circle distance in km between (lat, lon) pairs."""
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def modal_home(fixes, places=3):
    """The most common rounded (lat, lon) among `fixes`, as a stand-in for home when the backend's
    configured home coordinates are not at hand (a replay over the lake). Rounding to 3 decimals is
    about 100 m, finer than the 2 km uncertainty, so it only needs to find the commonest place."""
    counts = {}
    for _at, lat, lon, _acc in fixes:
        key = (round(lat, places), round(lon, places))
        counts[key] = counts.get(key, 0) + 1
    return max(counts, key=counts.get) if counts else None


def observe(user_id, install, fixes, now, home, stale_minutes=STALE_MINUTES):
    """The layer-1 state row for one install's owner, or None. `fixes`: (captured_at, lat, lon,
    accuracy_m) tuples, any order, naive UTC; `home`: (lat, lon) or None."""
    if home is None or not fixes:
        return None
    usable = [f for f in fixes if f[0] <= now]
    if not usable:
        return None
    newest = max(usable, key=lambda f: f[0])
    age = (now - newest[0]).total_seconds() / 60.0
    if age > stale_minutes:
        return None
    km = distance_km(home, (newest[1], newest[2]))
    if km >= FAR_KM:
        state = FAR
    elif km <= NEAR_KM:
        state = NEAR
    else:
        return None  # ambiguous at this accuracy: no evidence either way
    return Inference(
        kind="state",
        subject_type="user",
        subject_id=str(user_id),
        signal=SIGNAL,
        learner=NAME,
        learner_version=VERSION,
        window_start=newest[0],
        window_end=now,
        observed={"state": state, "distance_km": round(km, 1), "age_minutes": round(age)},
        confidence=CONFIDENCE,
        evidence={"family": FAMILY, "install": install, "accuracy_m": newest[3]},
        expires_at=now + timedelta(minutes=stale_minutes),
    )
