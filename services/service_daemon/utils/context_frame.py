#!/usr/bin/python

"""
Per-cycle context frame for MyDaemon.decide_displays() (SA-4).

Before this, decide_displays()'s ~15 DISPLAY_RULES checks each independently opened their own
DB connection and re-derived their own context every ~60s cycle. Phase 0 investigation (see
todo/todo_context_frame.md) found these exact duplicates, all fixed by this frame:

- `environment` table read 3x/cycle: check_weather (city/description/low/high/subjective_feel),
  check_weather_advisory (forecast_rain_probability), check_gatherings
  (description/subjective_feel) -- one row, three separate queries.
- The environment's timezone read 4x/cycle via db_utils.get_env_local_time(), each call opening
  its own fresh connection: check_gatherings, check_party_advisory, check_wind_down_signal,
  check_mood.
- calendar_utils.get_upcoming_events() called 2x/cycle: check_events, check_focus_needed.
- spotify_utils.get_playback_state() called 2x/cycle: check_now_playing, check_party_advisory.
- The `config` table's NOW_PLAYING_CONFIG_KEY row read 2x/cycle: check_now_playing (to detect a
  change), check_cross_surface_continuity (to check for a recent pause).
- MyDaemon._read_fresh_attention_telemetry() and ._attention_telemetry_trend() each called
  2x/cycle: check_attention_focus, check_wind_down_signal -- the trend query is the single most
  expensive duplicate (a 14-day history scan).

This module holds the frame's data container (`ContextFrame`) and the two brand-new standalone
fetchers this refactor needed (`fetch_online_devices`, `fetch_environment_snapshot`) -- neither
existed as a reusable function before, they were inline in check_household_composition()/
check_weather(). `MyDaemon.build_context_frame()` (alfr3ddaemon.py) is what actually assembles a
frame each cycle -- kept there, not here, since it also needs to call MyDaemon's existing private
helpers (_read_config_json, _read_fresh_attention_telemetry, _attention_telemetry_trend) rather
than reimplement them.

Every field is independently nullable: one integration failing (Spotify unreachable, a
particular query erroring) must never prevent unrelated fields, or the cards that depend on
them, from being built. The frame is immutable in spirit (built once, read-only for the rest of
the cycle) and thrown away at the end of it -- no cross-cycle caching.
"""

import logging
import os

import pymysql

logger = logging.getLogger("DaemonLog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")


class ContextFrame:
    """Plain data container for one decide_displays() cycle's shared signals. No type hints
    (see AGENTS.md) -- every attribute defaults to None and is populated (or left None on
    failure) by MyDaemon.build_context_frame()."""

    def __init__(self):
        self.now = None
        self.local_dt = None
        self.day_mood = None
        self.day_ctx = None  # common.day_context.DayContext for this cycle
        self.upcoming_events = None
        self.online_devices = None
        self.smarthome_online = None
        self.environment = None
        self.playback = None
        self.persisted_now_playing = None
        self.launcher_context = None


class LauncherContext:
    """Sub-namespace for launcher-reported signals -- surface_state (SA cross-surface
    continuity), attention_snapshot (the fresh reported snapshot), attention_trend (the
    household's rolling median, SA-2). Grouped together since they're all read from
    launcher-reported `config`/`attention_telemetry_history` state, not because callers need to
    treat them as one thing."""

    def __init__(self):
        self.surface_state = None
        self.attention_snapshot = None
        self.attention_trend = None


def fetch_online_devices():
    """Every currently-online device, joined to its claiming user (if any) -- the same query
    check_household_composition() used to run inline. Returns a dict with `known_names` (sorted
    list of distinct claiming usernames), `known_count`, `unknown_count`, or None on a DB error.
    Not scoped to a single environment -- devices aren't environment-scoped in this schema.
    """
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT u.username, d.name
            FROM device d
            JOIN states s ON d.state = s.id
            LEFT JOIN user u ON d.user_id = u.id
                AND u.username NOT IN ('unknown', 'alfr3d')
            WHERE s.state = 'online'
            """
        )
        rows = cursor.fetchall()
        known_names = sorted({row[0] for row in rows if row[0]})
        return {
            "rows": rows,
            "known_names": known_names,
            "known_count": len(known_names),
            "unknown_count": sum(1 for row in rows if not row[0]),
        }
    except pymysql.Error as e:
        logger.error(f"Context frame: online_devices fetch error: {e}")
        return None
    finally:
        if db:
            db.close()


def fetch_smarthome_online():
    """Names of currently-on `smarthome_devices` (Home Assistant/SmartThings) -- new for
    Phase 3's "empty house, things still on" rule (SA-4), which needed this alongside
    `online_devices` and `day_mood` and couldn't be written without it. `online` is a plain
    BOOLEAN column ha_utils.sync_devices() already maintains (`state == "on"`), not something
    that needs parsing out of the `last_state` JSON blob. Returns a list (possibly empty), or
    None on a DB error.
    """
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute("SELECT name FROM smarthome_devices WHERE online = TRUE")
        return sorted(name for (name,) in cursor.fetchall() if name)
    except pymysql.Error as e:
        logger.error(f"Context frame: smarthome_online fetch error: {e}")
        return None
    finally:
        if db:
            db.close()


def fetch_environment_snapshot(env_name):
    """This household's `environment` row -- current conditions and forecast columns combined
    into the one query check_weather()/check_weather_advisory()/check_gatherings() each ran
    separately before. Returns a dict, or None if there's no row yet or on a DB error."""
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT city, description, low, high, subjective_feel, forecast_rain_probability "
            "FROM environment WHERE name = %s",
            (env_name,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        city, description, low, high, subjective_feel, forecast_rain_probability = row
        return {
            "city": city,
            "description": description,
            "low": low,
            "high": high,
            "subjective_feel": subjective_feel,
            "forecast_rain_probability": forecast_rain_probability,
        }
    except pymysql.Error as e:
        logger.error(f"Context frame: environment fetch error: {e}")
        return None
    finally:
        if db:
            db.close()
