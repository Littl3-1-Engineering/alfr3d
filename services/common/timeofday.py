"""Pure time-of-day bucketing shared across services.

stdlib-only (no DB, no Kafka, no service imports) so anything can import it,
including deliberately dependency-light modules like
``service_daemon/utils/mood_utils.py``. The DB-backed, routine-aware layer that
knows the household's actual wake/sleep/sun times lives in
``common/day_context.py`` -- this module is only the clock math everyone agrees
on, in one place instead of three.
"""


def coarse_bucket(hour):
    """Bucket an env-local hour (0-23) into 'morning'/'day'/'evening'/'night'.

    This is the 4-way view the music recommender and the day-mood energy table
    use. It used to be copy-pasted in ``common.spotify_utils`` and
    ``service_daemon/utils/mood_utils.py`` with a "keep these in sync" comment
    on both -- now there is one definition.
    """
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


# Fine-grained parts of the day. The boundaries that a routine anchors
# (Morning / Bedtime / Sunrise / Sunset) are resolved in day_context.py against
# the live ``routines`` table; the daytime middle (morning/midday/afternoon) is
# plain clock hours -- user decision 2026-09-04: wake, sleep and the sun are the
# boundaries worth tuning per household, the middle of the day is not.
PARTS = ("night", "dawn", "morning", "midday", "afternoon", "evening", "wind_down")

MIDDAY_START_HOUR = 11
AFTERNOON_START_HOUR = 14
EVENING_FALLBACK_HOUR = 17  # only used when sunset is unavailable

# Fine part -> spoken greeting. Overnight has no time-of-day greeting on
# purpose; callers fall back to a plain "Hello".
GREETINGS = {
    "dawn": "Good morning",
    "morning": "Good morning",
    "midday": "Good afternoon",
    "afternoon": "Good afternoon",
    "evening": "Good evening",
    "wind_down": "Good evening",
    "night": "",
}

_FINE_TO_COARSE = {
    "dawn": "morning",
    "morning": "morning",
    "midday": "day",
    "afternoon": "day",
    "evening": "evening",
    "wind_down": "night",
    "night": "night",
}


def coarse_of(part):
    """Collapse a fine part-of-day (see PARTS) to the coarse 4-way bucket."""
    return _FINE_TO_COARSE.get(part, "night")
