"""The household's single source of truth for "what time is it, is Alfr3d
awake, and how should it greet."

Built from the ``environment`` row (timezone, sunrise, sunset) plus the
Sunrise / Morning / Sunset / Bedtime rows in the ``routines`` table -- the same
rows the user tunes in the Matrix UI. Edit the Bedtime routine and the mute
window, the idle-quip wind-down, and the "good evening" cutoff all move with
it, because they all read this.

Before this, six places rolled their own clock math and disagreed:
``check_mute`` (waking hours, from the routines), ``check_routines`` (is_night,
from the sun), the music/mood bucketers (fixed hours, x3), the personality
late-night nudge (a ``context.hour`` column that was never written), and the
greeting text (which had no time awareness at all, so "Hello sunshine" at
22:00 became "Good morning").

One small query per call. Callers that need it several times in a pass (the
daemon cycle) should build it once and pass it around -- e.g. it rides on the
SA ``ContextFrame`` as ``frame.day_ctx``.
"""

import logging
import time as _time
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta

from .db_pool import get_connection
from . import db_utils
from . import timeofday

logger = logging.getLogger("DayContext")

# Minutes before the Bedtime routine during which Alfr3d stops *volunteering*
# idle chatter. Answers to direct requests and the Bedtime routine's own quip
# still go through -- this only silences the unprompted "be a smartass" timer.
WIND_DOWN_MARGIN_MIN = 45

# get_day_context() is called several times per daemon cycle and once per LLM
# speak. part_of_day / greeting / the wind-down boundary only move on the order
# of minutes, so a short TTL cache is safe and spares the DB (and a slow
# connection-failure path) the repeat work.
_CACHE_TTL_SEC = 20
_cache = {}  # env_name -> (monotonic_built_at, DayContext)


def clear_cache():
    _cache.clear()


_DEFAULT_WAKE = dtime(6, 30)
_DEFAULT_BED = dtime(22, 0)


@dataclass(frozen=True)
class DayContext:
    now: datetime  # env-local, naive
    part_of_day: str  # one of timeofday.PARTS
    greeting: str  # "Good morning" etc.; "" overnight
    is_waking_hours: bool  # Morning routine <= now < Bedtime routine
    is_daylight: bool  # sunrise <= now < sunset
    minutes_to_bedtime: int  # None once past bedtime
    wake_time: dtime
    bed_time: dtime

    @property
    def hour(self):
        return self.now.hour

    @property
    def coarse_part(self):
        """The 4-way morning/day/evening/night view for the music + mood code."""
        return timeofday.coarse_of(self.part_of_day)

    @property
    def in_wind_down(self):
        return self.part_of_day == "wind_down"

    def describe(self):
        """One-line summary for the LLM system prompt and logs."""
        lit = "daytime" if self.is_daylight else "nighttime"
        return f"{self.now:%A %H:%M} ({self.part_of_day}, {lit})"


def _to_time(td, default):
    """A ``routines.time`` value is a timedelta since midnight; -> datetime.time."""
    if td is None:
        return default
    try:
        total = int(td.total_seconds())
    except AttributeError:
        return default
    return dtime(hour=(total // 3600) % 24, minute=(total // 60) % 60)


def _project(now, sun):
    """Project a stored sunrise/sunset onto ``now``'s date (the environment row
    carries whatever date the last weather refresh wrote; only the clock time
    matters here)."""
    if not sun:
        return None
    return now.replace(hour=sun.hour, minute=sun.minute, second=0, microsecond=0)


def get_day_context(env_name, now=None):
    """Build the DayContext for ``env_name``. ``now`` may be supplied (env-local,
    naive) to avoid a redundant timezone lookup when the caller already has it.

    Result is cached per env for ~20s (see _CACHE_TTL_SEC)."""
    cached = _cache.get(env_name)
    if cached and (_time.monotonic() - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    local_now = now or db_utils.get_env_local_time(env_name)

    sunrise = sunset = wake_td = bed_td = None
    db = None
    try:
        db = get_connection()
        cur = db.cursor()
        cur.execute(
            """
            SELECT e.sunrise, e.sunset,
                   MAX(CASE WHEN r.name = 'Morning' THEN r.time END),
                   MAX(CASE WHEN r.name = 'Bedtime' THEN r.time END)
            FROM environment e
            LEFT JOIN routines r
                   ON r.environment_id = e.id AND r.name IN ('Morning', 'Bedtime')
            WHERE e.name = %s
            GROUP BY e.id, e.sunrise, e.sunset
            """,
            (env_name,),
        )
        row = cur.fetchone()
        if row:
            sunrise, sunset, wake_td, bed_td = row
    except Exception as e:  # defensive -- fall back to clock-only defaults
        logger.warning(f"DayContext DB read failed ({e}); using clock-only fallback")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    ctx = _assemble(
        local_now,
        _to_time(wake_td, _DEFAULT_WAKE),
        _to_time(bed_td, _DEFAULT_BED),
        _project(local_now, sunrise),
        _project(local_now, sunset),
    )
    _cache[env_name] = (_time.monotonic(), ctx)
    return ctx


def _assemble(now, wake_t, bed_t, sunrise, sunset):
    day = now.date()
    wake_dt = datetime.combine(day, wake_t)
    bed_dt = datetime.combine(day, bed_t)
    if bed_dt <= wake_dt:  # bedtime after midnight (e.g. 01:00)
        bed_dt += timedelta(days=1)

    wind_down_dt = bed_dt - timedelta(minutes=WIND_DOWN_MARGIN_MIN)
    is_waking = wake_dt <= now < bed_dt
    is_daylight = bool(sunrise and sunset and sunrise <= now < sunset)
    mins_to_bed = int((bed_dt - now).total_seconds() // 60) if now < bed_dt else None

    part = _classify(now, wake_dt, bed_dt, wind_down_dt, sunrise, sunset)
    return DayContext(
        now=now,
        part_of_day=part,
        greeting=timeofday.GREETINGS.get(part, ""),
        is_waking_hours=is_waking,
        is_daylight=is_daylight,
        minutes_to_bedtime=mins_to_bed,
        wake_time=wake_t,
        bed_time=bed_t,
    )


def _classify(now, wake_dt, bed_dt, wind_down_dt, sunrise, sunset):
    if now < wake_dt or now >= bed_dt:
        return "night"
    if now >= wind_down_dt:
        return "wind_down"
    if sunrise and now < sunrise:
        return "dawn"
    hour = now.hour
    if hour < timeofday.MIDDAY_START_HOUR:
        return "morning"
    if hour < timeofday.AFTERNOON_START_HOUR:
        return "midday"
    evening_start = sunset or now.replace(
        hour=timeofday.EVENING_FALLBACK_HOUR, minute=0, second=0, microsecond=0
    )
    return "evening" if now >= evening_start else "afternoon"
