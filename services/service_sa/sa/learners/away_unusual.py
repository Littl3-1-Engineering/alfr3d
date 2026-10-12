"""Away-unusual (LF-6): a person is out when their usual rhythm says they should be home.

The second LAYER-2 inference. It reads layer-1 rows only, never raw data:

- the person's `presence.home` deviation where the observed state is "away" (the presence
  learner has already required >= 3 bits of surprise and >= 60 minutes away),
- `device.online` deviations (offline when usually on) for devices that person owns,
- a `calendar.busy` row (an event covers now) EXPLAINS the absence: it discounts the surprise
  (layer2.Rule.explained_discount) rather than voting, so a booked absence stops being unusual,
- optional parents from other source families (Home Assistant trackers) when a learner for them
  exists.

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

from sa import layer2
from sa.learners import device_rhythm, presence

NAME = "away_unusual"
VERSION = "1"
SIGNAL = "presence.away_unusual"

MIN_SURPRISE_BITS = 3.0
CORROBORATION_FLOOR = 0.6
FAMILY_NETWORK = "network"


def _is_away(inference):
    return (inference.observed or {}).get("state") in ("away", "offline")


class AwayUnusualRule(layer2.Rule):
    """One group per person with a fresh away presence deviation. ctx: {"owners": {device_id:
    user_id}, "owned_with_profile": {user_id: n}}, loaded by the runner."""

    name = NAME
    version = VERSION
    signal = SIGNAL
    subject_type = "user"
    min_bits = MIN_SURPRISE_BITS
    corroboration_floor = CORROBORATION_FLOOR

    def groups(self, parents, ctx):
        owners = ctx.get("owners", {})
        owned = ctx.get("owned_with_profile", {})
        devices = {}
        for parent in parents:
            if parent.signal == device_rhythm.SIGNAL_AVAILABILITY and _is_away(parent):
                user = owners.get(str(parent.subject_id))
                if user is not None:
                    devices.setdefault(str(user), []).append(parent)
        # A booked event covering now explains an absence: it discounts the surprise instead of
        # silencing the result (the household calendar has no per-person owner).
        explained = [p for p in parents if p.signal == layer2.SIGNAL_CALENDAR_BUSY]
        out = []
        for parent in parents:
            if parent.signal != presence.SIGNAL or parent.kind != "deviation":
                continue
            if not _is_away(parent):
                continue
            user = str(parent.subject_id)
            mine = devices.get(user, [])
            with_profile = owned.get(user, 0)
            out.append(
                layer2.Group(
                    user,
                    parent,
                    [parent] + mine,
                    share=min(1.0, len(mine) / with_profile) if with_profile else None,
                    explained_by=explained,
                    evidence={
                        "username": (parent.evidence or {}).get("username"),
                        "devices_offline": len(mine),
                        "devices_with_profile": with_profile,
                    },
                )
            )
        return out

    def observed(self, group):
        return {
            "state": "away",
            "away_minutes": (group.anchor.observed or {}).get("away_minutes"),
        }


RULE = AwayUnusualRule()


def combine(
    user_id, username, presence_inf, device_infs, owned_with_profile, now, extra=(), explained_by=()
):
    """The layer-2 inference for one person, or None, from already-scored parents. A thin wrapper
    over the generic rule for callers (and replays) that hold Inference objects rather than rows.

    presence_inf: that person's presence.home deviation (None if there isn't one);
    device_infs: device.online deviations for devices they own;
    owned_with_profile: how many of their devices have a rhythm profile (the corroboration base);
    extra: further layer-1 deviations from other families (each needs evidence["family"]);
    explained_by: rows (a booked calendar event) that make the absence less surprising.
    """
    if presence_inf is None or presence_inf.kind != "deviation" or not _is_away(presence_inf):
        return None
    devices_off = [d for d in device_infs if _is_away(d)]
    share = min(1.0, len(devices_off) / owned_with_profile) if owned_with_profile else None
    group = layer2.Group(
        user_id,
        presence_inf,
        [presence_inf] + devices_off + list(extra),
        share=share,
        explained_by=explained_by,
        evidence={
            "username": username,
            "devices_offline": len(devices_off),
            "devices_with_profile": owned_with_profile,
        },
    )
    return layer2.fuse(RULE, group, now)


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
