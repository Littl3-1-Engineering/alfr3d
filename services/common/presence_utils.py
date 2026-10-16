"""Shared "who is on the network" classification for online devices.

Used by service_sa's context frame and service_api's context snapshot so the two never
disagree about what counts as an unrecognized device.
"""

# `alfr3d` owns the house's own infrastructure (smart speakers, cameras, hubs, sensors, the
# router): not a household member, but not an intruder either.
INFRASTRUCTURE_USERNAMES = frozenset({"alfr3d"})
# `unknown` is the explicit "nobody has claimed this MAC" owner, same as no owner at all.
UNCLAIMED_USERNAMES = frozenset({"unknown"})


def summarize_online_devices(rows):
    """Split (owner_username_or_None, device_name) rows for online devices into household
    members, infrastructure and unrecognized devices.

    Returns `known_names` (sorted distinct member usernames), `known_count`, `unknown_count`
    (devices with no owner or the `unknown` owner only) and `infrastructure_count`.
    """
    known_names = set()
    unknown_count = 0
    infrastructure_count = 0
    for row in rows:
        username = row[0]
        if not username or username in UNCLAIMED_USERNAMES:
            unknown_count += 1
        elif username in INFRASTRUCTURE_USERNAMES:
            infrastructure_count += 1
        else:
            known_names.add(username)
    known = sorted(known_names)
    return {
        "known_names": known,
        "known_count": len(known),
        "unknown_count": unknown_count,
        "infrastructure_count": infrastructure_count,
    }
