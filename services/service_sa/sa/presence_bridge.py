"""How long a phone may go unseen before its owner counts as gone (todo/sa/SA_ROADMAP.md, Step 1).

Silver turns phone sightings into presence intervals: sightings no further apart than the bridge
belong to one stay. One constant for everybody is wrong in both directions. A phone that sleeps
(arp skips it for 20-45 minutes while its owner sits at home) needs a long bridge or every evening
splits into false departures; a phone that never sleeps needs a short one or every walk under the
bridge disappears into a "stay". Measured 2026-11-01 over four weeks, gaps of 20-45 minutes: Jenna
212 (92 of them between midnight and 7am), Athos 18 (3 at night), and for Athos 14 of 17 such
gaps had a Deck cellular report inside, i.e. real outings.

So the bridge is learned per person from the one time the phone is almost surely at home: the
night. The gaps between consecutive sightings that begin between NIGHT_START_HOUR and
NIGHT_END_HOUR local time and are shorter than MAX_BRIDGE_MINUTES are naps; the bridge is a high
quantile of them. A phone that rarely naps gets the floor, a person with too few observed nights
gets the old default. Pure functions, no I/O, so silver, the nightly fit and the tests share them.
"""

import math

DEFAULT_BRIDGE_MINUTES = 45  # the pre-2026-11 constant: used until a person has enough nights
MIN_BRIDGE_MINUTES = 15
MAX_BRIDGE_MINUTES = 60
AMBIGUOUS_GAP_MINUTES = 10  # gaps shorter than this are arp skipping a device, never evidence
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 6
NAP_QUANTILE = 0.95
MIN_NIGHTS = 14  # nights with a sighting needed to trust the phone's night behaviour
MIN_NAP_GAPS = 5  # fewer naps than this over MIN_NIGHTS nights: the phone does not nap
WINDOW_DAYS = 56
ROUND_TO = 5


def is_nap(gap_minutes):
    return AMBIGUOUS_GAP_MINUTES <= gap_minutes < MAX_BRIDGE_MINUTES


def decide(night_gaps, nights):
    """(bridge_minutes, basis). night_gaps: gaps in minutes that began at night; only naps count.
    nights: local dates in the window that have a sighting between the night hours."""
    naps = sorted(g for g in night_gaps if is_nap(g))
    if nights < MIN_NIGHTS:
        return DEFAULT_BRIDGE_MINUTES, "default"
    if len(naps) < MIN_NAP_GAPS:
        return MIN_BRIDGE_MINUTES, "quiet_phone"
    index = min(len(naps) - 1, math.ceil(NAP_QUANTILE * len(naps)) - 1)
    minutes = math.ceil(naps[index] / ROUND_TO) * ROUND_TO
    return max(MIN_BRIDGE_MINUTES, min(MAX_BRIDGE_MINUTES, minutes)), "naps"


def bridge_for(bridges, user_id):
    """Minutes for one person from {user_id: minutes} (keys may be int or str), or the default."""
    if not bridges:
        return DEFAULT_BRIDGE_MINUTES
    return bridges.get(user_id, bridges.get(str(user_id), DEFAULT_BRIDGE_MINUTES))
