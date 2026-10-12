"""Day-off (LF-6): a person is home on a day they are usually out, and nothing is booked.

The third LAYER-2 inference, reading layer-1 rows only: the person's `presence.home` deviation
where the observed state is "home" (improbable at this weekday and hour). The household calendar is
an independent family of evidence, but it carries no probability of its own, so it corroborates:
an empty calendar today makes "day off" believable, a booked one (a work-from-home day full of
meetings) lowers confidence to the corroboration floor. Probability is the presence deviation's.

One result per person per day: the group's window starts at the local midnight
(ctx["day_start_utc"]), so the hourly presence deviations upsert a single row.
"""

from sa import layer2
from sa.learners import presence

NAME = "day_off"
VERSION = "1"
SIGNAL = "presence.day_off"
MIN_SURPRISE_BITS = 3.0
CORROBORATION_FLOOR = 0.3


def _is_home(inference):
    return (inference.observed or {}).get("state") == "home"


class DayOffRule(layer2.Rule):
    """ctx: {"day_start_utc": naive UTC local midnight, "calendar_events_today": int or None}.
    With no calendar count the rule still fires, uncorroborated."""

    name = NAME
    version = VERSION
    signal = SIGNAL
    subject_type = "user"
    min_bits = MIN_SURPRISE_BITS
    corroboration_floor = CORROBORATION_FLOOR

    def groups(self, parents, ctx):
        events = ctx.get("calendar_events_today")
        share = None if events is None else (1.0 if events == 0 else 0.0)
        out = []
        for parent in parents:
            if parent.signal != presence.SIGNAL or parent.kind != "deviation":
                continue
            if not _is_home(parent):
                continue
            out.append(
                layer2.Group(
                    parent.subject_id,
                    parent,
                    [parent],
                    share=share,
                    window_start=ctx.get("day_start_utc"),
                    evidence={
                        "username": (parent.evidence or {}).get("username"),
                        "calendar_events_today": events,
                    },
                )
            )
        return out


RULE = DayOffRule()
