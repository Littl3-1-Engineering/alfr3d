#!/usr/bin/python

"""
Shared "day mood" primitive for Alfr3d Daemon.

Pure, dependency-free (stdlib `datetime` only) time-of-day and baseline-energy
bucketing, factored out of what used to be inline hour math in
`alfr3ddaemon.check_gatherings()`. `check_gatherings()` and the new
`check_mood()` situational-awareness card both call `get_day_mood()` so the
"what part of the day/week is it" logic lives in exactly one place.

The time-of-day boundaries intentionally mirror
`common.spotify_utils._normalize_time_of_day()` (6-12 morning, 12-18 day,
18-22 evening, else night). They are duplicated rather than imported: this
module stays dependency-free, and `common/` (shared with `service_api`) must
not import from a single service's `utils/` package. If the boundaries in
`common.spotify_utils._normalize_time_of_day()` ever change, update
`_bucket_time_of_day()` below to match.
"""

from datetime import datetime

_WEEKEND_DAYS = ("Saturday", "Sunday")

# Baseline energy (0.0-1.0) before any situational adjustment (people count,
# weather, etc. — those stay in common.spotify_utils.recommend()).
_BASE_ENERGY_BY_TIME_OF_DAY = {
    "morning": 0.35,
    "day": 0.50,
    "evening": 0.55,
    "night": 0.30,
}

# Simple, explainable weekend rule: Friday evening/night through all of
# Saturday/Sunday get a flat bump to the evening/night baseline, standing in
# for "people are more likely to be relaxed/social heading into a weekend."
# A Tuesday evening stays at the plain evening baseline; a Friday or Saturday
# evening/night does not.
_WEEKEND_ENERGY_BONUS = 0.15


def _bucket_time_of_day(hour):
    """Bucket an hour (0-23) into 'morning'/'day'/'evening'/'night'.

    Mirrors common.spotify_utils._normalize_time_of_day() — see module
    docstring for why this is duplicated rather than imported.
    """
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def get_day_mood(now=None):
    """Compute a simple, explainable day-mood snapshot.

    Args:
        now: optional `datetime` to evaluate; defaults to `datetime.now()`
             when omitted so callers can pass a fixed time in tests. Callers
             that care about the household's local time (e.g. the daemon)
             should pass `db_utils.get_env_local_time(ENV_NAME)` explicitly.

    Returns:
        dict with keys:
            time_of_day: 'morning' | 'day' | 'evening' | 'night'
            day_of_week: full weekday name, e.g. 'Tuesday'
            is_weekend: True for Saturday/Sunday
            base_energy: float 0.0-1.0, same scale as
                common.spotify_utils.recommend()'s 'energy' output
    """
    if now is None:
        now = datetime.now()

    time_of_day = _bucket_time_of_day(now.hour)
    day_of_week = now.strftime("%A")
    is_weekend = day_of_week in _WEEKEND_DAYS
    is_friday_wind_up = day_of_week == "Friday" and time_of_day in ("evening", "night")

    base_energy = _BASE_ENERGY_BY_TIME_OF_DAY[time_of_day]
    if (is_weekend or is_friday_wind_up) and time_of_day in ("evening", "night"):
        base_energy = min(1.0, base_energy + _WEEKEND_ENERGY_BONUS)

    return {
        "time_of_day": time_of_day,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "base_energy": round(base_energy, 2),
    }
