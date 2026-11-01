"""Deck network observer (LF-6): a second, independent family for presence rules.

Arp-scan sightings are the presence learner's only input, so every layer-1 presence row shares one
source family. The Deck reports its own network type (`deck_context_history.network_type`) from
the phone itself, which does not depend on arp at all. Phase 0 (todo/sa/todo_lf6_layer2.md, Athos,
2026-10-11..11-01): a single cellular report is noise (90 % fall inside an arp-home interval), but
cellular sustained for 30+ minutes is outside the house (9 % arp-home), and sustained wifi inside
an arp-away stretch is the sleeping-phone case where arp is wrong.

So this observer writes a layer-1 STATE row per person, never a probability (wifi is not proof of
home, cellular is not proof of away). Layer 2 reads it two ways (learners/away_unusual.py):
sustained cellular corroborates an absence, sustained wifi explains it away.

It works for any household with at least one reporting Deck. A person with no Deck, or whose Deck
has never sent a location fix (the link from install to user), simply has no row: absence of the
row is "no evidence", never evidence.

`sustained_state` is a pure function over (observed_at, network_type) pairs so a replay needs no
database. The staleness bar comes from each install's own report cadence, not a constant.
"""

from datetime import timedelta
from statistics import median

from sa.learners.base import Inference

NAME = "deck_observer"
VERSION = "1"
SIGNAL = "deck.network"
FAMILY = "deck"

OUT = "out"  # sustained cellular
WIFI = "wifi"  # sustained wifi
_STATE_BY_TYPE = {"cellular": OUT, "wifi": WIFI}

# From the Phase 0 replay: runs of 30+ minutes separated outside from home; shorter ones did not.
MIN_SUSTAINED_MINUTES = 30
MIN_REPORTS = 2
# The newest report must be this many median report gaps old at most to count as "now".
STALE_GAPS = 2
# Below this many reports there is no cadence to measure; fall back to this staleness.
MIN_REPORTS_FOR_CADENCE = 10
FALLBACK_STALE_MINUTES = 20


def median_gap_minutes(times):
    """Median minutes between consecutive report times, or None with too few to measure."""
    times = sorted(times)
    if len(times) < MIN_REPORTS_FOR_CADENCE:
        return None
    return median((b - a).total_seconds() / 60.0 for a, b in zip(times, times[1:]))


def stale_minutes(gap_minutes):
    return FALLBACK_STALE_MINUTES if gap_minutes is None else STALE_GAPS * gap_minutes


def sustained_state(reports, now, gap_minutes=None):
    """(state, since, n_reports) or None. `reports`: (observed_at, network_type) pairs, any order.
    The newest report decides the state; it counts only if fresh, only for cellular or wifi, and
    only once that same network has been reported continuously for MIN_SUSTAINED_MINUTES across at
    least MIN_REPORTS reports (an unknown or other network ends the run)."""
    ordered = sorted(reports, reverse=True)
    if not ordered:
        return None
    newest_at, newest_type = ordered[0]
    state = _STATE_BY_TYPE.get(newest_type)
    if state is None or now - newest_at > timedelta(minutes=stale_minutes(gap_minutes)):
        return None
    since, count = newest_at, 0
    for at, kind in ordered:
        if kind != newest_type:
            break
        since, count = at, count + 1
    if count < MIN_REPORTS or newest_at - since < timedelta(minutes=MIN_SUSTAINED_MINUTES):
        return None
    return state, since, count


def observe(user_id, install_id, reports, now, gap_minutes=None):
    """The layer-1 state row for one person, or None."""
    found = sustained_state(reports, now, gap_minutes)
    if found is None:
        return None
    state, since, count = found
    return Inference(
        kind="state",
        subject_type="user",
        subject_id=user_id,
        signal=SIGNAL,
        learner=NAME,
        learner_version=VERSION,
        window_start=since,
        window_end=now.replace(microsecond=0),
        observed={"state": state},
        confidence=1.0,
        n_eff=count,
        evidence={"family": FAMILY, "install": str(install_id)[:8], "reports": count},
        expires_at=now + timedelta(minutes=10),
    )
