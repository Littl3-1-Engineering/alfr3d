#!/usr/bin/python

"""
This is the main Alfr3d daemon running most standard services
"""

# Copyright (c) 2010-2018 LiTtl3.1 Industries (LiTtl3.1).
# All rights reserved.
# This source code and any compilation or derivative thereof is the
# proprietary information of LiTtl3.1 Industries and is
# confidential in nature.
# Use of this source code is subject to the terms of the applicable
# LiTtl3.1 Industries license agreement.
#
# Under no circumstances is this component (or portion thereof) to be in any
# way affected or brought under the terms of any Open Source License without
# the prior express written permission of LiTtl3.1 Industries.
#
# For the purpose of this clause, the term Open Source Software/Component
# includes:
#
# (i) any software/component that requires as a condition of use, modification
# 	 and/or distribution of such software/component, that such software/
# 	 component:
# 	 a. be disclosed or distributed in source code form;
# 	 b. be licensed for the purpose of making derivative works; and/or
# (ii) any software/component that contains, is derived in any manner (in whole
# 	  or in part) from, or statically or dynamically links against any
# 	  software/component specified under (i).
#

# Standard library imports
import logging
import statistics
import time
import os  # used to allow execution of system level commands
import sys
from random import randint  # used for random number generator
import bisect
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
import orjson
import threading

# Third party imports
import pymysql
import schedule  # 3rd party lib used for alarm clock managment.
from utils import util_routines
from utils import (
    gmail_utils,
    calendar_utils,
    spotify_utils,
    mood_utils,
    focus_utils,
    now_playing_monitor,
    context_frame,
    routing_utils,
)
from kafka.errors import KafkaError
from kafka import KafkaConsumer  # user to write messages to Kafka

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer  # noqa: E402
from common import db_utils  # noqa: E402
from common import day_context  # noqa: E402
from common import timeofday  # noqa: E402

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)


# set up daemon things
# directories created in Dockerfile

# get main DB credentials
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

# How far ahead of a call-like event's start time check_focus_needed() will fire.
FOCUS_LEAD_MINUTES = 15

# Minimum forecast rain probability (%) for check_weather_advisory() to fire.
RAIN_ADVISORY_THRESHOLD = 30

# How far ahead the forecast checked by check_weather_advisory() looks.
FORECAST_HOURS_AHEAD = 6

# Spotify's own 0.0-1.0 "energy" audio feature above which check_party_advisory()
# considers what's actually playing to be genuinely high-energy, independent
# of ALFR3D's own (capped, on weeknights) recommendation.
PARTY_ADVISORY_ENERGY_THRESHOLD = 0.75

# Minimum time between check_party_advisory() spoken nudges, so a rowdy
# weeknight track doesn't get "it's a school night" repeated every polling
# cycle -- the card itself still refreshes every cycle, only the TTS nudge
# is rate-limited.
PARTY_ADVISORY_COOLDOWN_MINUTES = 60

# time of sunset/sunrise - defaults
# SUNSET_TIME = datetime.datetime.now().replace(hour=19, minute=0)
# SUNRISE_TIME = datetime.datetime.now().replace(hour=6, minute=30)
# BED_TIME = datetime.datetime.now().replace(hour=23, minute=00)

# various counters to be used for pacing spreadout functions
QUIP_START_TIME = time.time()
QUIP_WAIT_TIME = randint(5, 10)

# Last time check_party_advisory() spoke a nudge; 0.0 so the very first
# detection always speaks rather than waiting out a cooldown against an
# undefined "last time".
PARTY_ADVISORY_LAST_NUDGE_TIME = 0.0

# `config` table key check_now_playing() persists the last-seen track under,
# so the value survives daemon restarts and is queryable by other services.
NOW_PLAYING_CONFIG_KEY = "music_now_playing"

# `config` table key POST /api/context/surface-state (service_api/routes/context.py)
# writes the launcher's last-reported active surface/terminal-session state
# under; read by check_cross_surface_continuity() via _read_config_json().
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"

# check_cross_surface_continuity() only offers a resume for state reported/
# updated within this many minutes -- a paused track or edited routine from
# hours ago isn't "picking up where you left off" anymore.
CROSS_SURFACE_STALENESS_MINUTES = 45

# `config` table key POST /api/context/attention-telemetry writes the
# launcher's most recent rolling-window snapshot under; read by
# check_attention_focus() and check_wind_down_signal().
ATTENTION_TELEMETRY_CONFIG_KEY = "launcher_attention_telemetry"

# The launcher reports a fresh attention-telemetry snapshot every ~15
# minutes -- a snapshot older than this is treated as stale (device likely
# offline/asleep) rather than fed into either check below.
ATTENTION_TELEMETRY_STALENESS_MINUTES = 30

# check_attention_focus() fires when the reported window-switch count is at
# least this high -- a conservative starting point (roughly one switch per
# minute sustained over a ~15-minute report window) with no real telemetry
# yet to tune it against.
ATTENTION_FOCUS_MIN_SWITCHES = 15

# ...and only when media-category dwell is under this fraction of total
# dwell time -- high switching concentrated in media (e.g. flipping between
# a few apps while half-watching something) isn't "focus", it's the
# wind-down check's pattern instead.
ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION = 0.3

# check_wind_down_signal() fires when the reported unlock count is at least
# this high within the report window -- another conservative starting point.
WIND_DOWN_MIN_UNLOCKS = 5

# ...and only when media-category dwell is over this fraction of total dwell
# time -- the milestone's own "late-hour high unlock rate + social-app
# dwell" pattern.
WIND_DOWN_MIN_MEDIA_DWELL_FRACTION = 0.5

# check_attention_focus()/check_wind_down_signal() compare the current snapshot against this
# household's own rolling switch_count/unlock_count median (see _attention_telemetry_trend())
# once at least this many attention_telemetry_history rows exist -- "is this unusual for this
# household" rather than only "is this a big number in general". ~2 days at the launcher's
# 15-minute report cadence; a conservative starting point with no real telemetry yet to tune it
# against, same caveat as ENTITY_BASELINE_MIN_SAMPLES. Below this floor, both checks fall back
# to the fixed thresholds above unchanged.
ATTENTION_TREND_MIN_SAMPLES = 200

# How far back _attention_telemetry_trend() looks when computing the household's median
# switch_count/unlock_count.
ATTENTION_TREND_LOOKBACK_DAYS = 14

# Grace added on top of the household's own median switch_count/unlock_count before either
# check fires on the trend path -- same "small grace window so a marginally-above-typical value
# doesn't trigger every cycle" reasoning as RHYTHM_BREAK_GRACE_MINUTES.
ATTENTION_FOCUS_TREND_GRACE_SWITCHES = 5
WIND_DOWN_TREND_GRACE_UNLOCKS = 2

# How long an attention_telemetry_history row survives before
# prune_attention_telemetry_history() deletes it -- same reasoning and default as
# HOUSEHOLD_EVENTS_RETENTION_DAYS, much lower actual volume (one row per launcher report, ~15
# min cadence, vs. one per event-stream message).
ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS = int(
    os.environ.get("ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS", "90")
)


# decide_displays()'s suppression pass (SA-1) identifies a card as (rule_id, subject_key) --
# DISPLAY_RULES' own id, not the card's own "mode" field (which collides: check_gatherings,
# rule id "music", and check_now_playing, rule id "now_playing", both stamp "mode": "music" on
# their card). Most rules are singleton -- there's only one slot to suppress regardless of what
# the content currently says (dismissing "now playing" should mean "stop telling me what's
# playing for a while", not "I've seen this exact track before"), so subject_key defaults to "".
# Only rules that can legitimately recur for different underlying entities get a real one, via
# CARD_SUBJECT_KEY_EXTRACTORS below -- dismissing one device's rhythm-break card must not
# suppress a different device's.
def _cross_surface_continuity_subject_key(card):
    return f"{card.get('resume_type')}:{card.get('resume_target')}"


CARD_SUBJECT_KEY_EXTRACTORS = {
    "rhythm_break_anomaly": lambda card: card.get("entity_name") or "",
    "cross_surface_continuity": _cross_surface_continuity_subject_key,
    # SA-3: departure_anomaly is rhythm_break_anomaly's human analogue -- dismissing one
    # resident's "still home" card must not suppress a different resident's.
    "departure_anomaly": lambda card: card.get("entity_name") or "",
}

# Cards whose `urgent` field is true are never suppressed regardless of interaction history --
# household_composition's elevated variant (an unrecognized device on the network) is the only
# one today, but this is a generic field check so any future rule can opt in the same way.
CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD = "urgent"

# decide_displays()'s suppression pass looks at up to this many of a card identity's most recent
# card_interactions rows -- must cover both the cooldown check (just the latest row) and the
# repetition-damping run-length count below.
CARD_SUPPRESSION_HISTORY_LIMIT = 10

# A card identity whose most recent interaction is "dismissed" is suppressed for this many
# minutes before it's allowed to show again -- a conservative starting point, no real
# interaction data yet to tune it against (same caveat as every other threshold in this file).
# Per-mode override via CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES = 60
CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE = {}

# A card identity shown this many cycles in a row with no interaction at all (no dismiss, no
# tap) gets suppressed until its underlying state changes (i.e. until something -- a different
# device, a content change on a singleton rule -- gives it a new identity, or a real interaction
# resets the run). Per-mode override via CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES = 20
CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE = {}

# How far back compute_entity_baselines() looks when reconstructing on/off
# sessions from device_history to build each device's rhythm baseline.
ENTITY_BASELINE_LOOKBACK_DAYS = 30

# Minimum complete on/off sessions before a device gets a baseline row at all --
# below this, a "typical" pattern isn't meaningfully established yet, and
# publishing one would produce noisy false-positive anomalies.
ENTITY_BASELINE_MIN_SAMPLES = 5

# How long a household_events row survives before prune_household_events()
# deletes it. household_events is written to on every event-stream message
# (see service_api's consume_events()), making it the highest-volume table
# in the schema -- see todo/todo_household_event_log.md for real row-growth
# numbers before raising this default.
HOUSEHOLD_EVENTS_RETENTION_DAYS = int(os.environ.get("HOUSEHOLD_EVENTS_RETENTION_DAYS", "90"))

# check_rhythm_break_anomaly() only fires this many minutes past a device's
# typical_daily_max on-duration -- a small grace window so a session that's
# only marginally longer than usual doesn't trigger every cycle.
RHYTHM_BREAK_GRACE_MINUTES = 15

# check_departure_anomaly() (SA-3): how far back device_history is scanned when computing a
# resident's per-weekday/weekend departure-hour baseline. Longer than ENTITY_BASELINE_LOOKBACK_DAYS
# (30d) deliberately -- splitting into weekday/weekend buckets roughly quarters the sample size a
# device baseline gets from the same window, and the confirmed-home-overnight anchor
# (_departure_hours_by_bucket()) rejects many days outright. Verified against this household's
# real history (todo/todo_departure_anomaly.md): 60 days left every resident under the sample
# floor; 120 days was the first window where multiple residents actually cleared it. 180 would
# match device_history's own retention ceiling exactly, leaving no margin before rows this
# window depends on get pruned daily -- 120 leaves a 60-day cushion.
DEPARTURE_BASELINE_LOOKBACK_DAYS = 120

# A gap this long between consecutive device_history writes for a claimed device is treated as a
# genuine absence, not scan noise -- service_device's own check_offline_devices() only flips a
# device to 'offline' once its last_online is stale by 30 minutes, so any gap at or above that
# (+1 minute buffer) reflects an already-confirmed offline transition, not scan jitter.
DEPARTURE_GAP_MINUTES = 31

# A resident's per-day-bucket (weekday/weekend) departure baseline needs at least this many
# observed first-departure days before check_departure_anomaly() trusts it -- same "degrade to
# silence below a reliability floor" precedent as ENTITY_BASELINE_MIN_SAMPLES/
# ATTENTION_TREND_MIN_SAMPLES elsewhere in this file.
DEPARTURE_BASELINE_MIN_SAMPLES = 8

# check_departure_anomaly() also requires the baseline's observed hour range
# (typical_daily_max - typical_daily_min) to be at or under this many hours. The Phase 0 spike
# found some residents' real departure-hour history is too scattered (multi-hour spread, no
# real "typical" time) to be worth alerting on at all -- above this floor that household member
# simply gets no departure-anomaly baseline, rather than firing on noise dressed up as a pattern.
DEPARTURE_BASELINE_MAX_SPREAD_HOURS = 4

# How many hours past a resident's typical departure hour check_departure_anomaly() waits before
# firing -- a grace window so running a bit late on an otherwise-normal day doesn't trigger a
# card, mirroring RHYTHM_BREAK_GRACE_MINUTES's reasoning at the coarser (hour, not minute)
# granularity appropriate for a once-a-day event.
DEPARTURE_ANOMALY_GRACE_HOURS = 1.5

# check_travel() (SA-6): fires once the computed leave-by time is within this many minutes of
# frame.now, in either direction -- gives advance notice before the leave-by moment rather than
# only announcing it right as it arrives, but still stops mentioning it once it's meaningfully
# passed (a stale leave-by time is worse than no card).
TRAVEL_LEAD_MINUTES = 30

# SA-10: household-level baselines (entity_type='household'). Household is a singleton -- there's
# only one row per day_bucket regardless of household size -- so entity_id is a fixed sentinel,
# not a real foreign key into any table.
HOUSEHOLD_BASELINE_ENTITY_ID = 0

# How far back the household-level aggregate query scans device_history. Reuses
# DEPARTURE_BASELINE_LOOKBACK_DAYS's own reasoning (weekday/weekend bucketing roughly halves the
# sample size a straight daily count would get, and 120 days leaves a cushion under
# device_history's 180-day retention) rather than re-deriving a separate number for a
# conceptually-similar "how much history does a day-bucketed household baseline need" question.
HOUSEHOLD_BASELINE_LOOKBACK_DAYS = DEPARTURE_BASELINE_LOOKBACK_DAYS

# A household-level per-day-bucket baseline needs at least this many observed days before
# check_household_unusual_day() trusts it -- same "degrade to silence below a reliability floor"
# precedent as every other baseline-gated check in this file. Set a bit higher than
# DEPARTURE_BASELINE_MIN_SAMPLES (8): a household-wide "is today unusual" call is a broader,
# higher-consequence claim than one resident's departure time, and deserves more evidence first.
HOUSEHOLD_BASELINE_MIN_SAMPLES = 14

# check_household_unusual_day() requires BOTH the device-count range and the first-activity hour
# to deviate before firing -- a single off metric isn't "today is different," it's normal
# day-to-day noise. This is how far (in hours) today's first-activity hour must differ from
# typical_active_hour to count as part of that deviation.
HOUSEHOLD_FIRST_ACTIVITY_HOUR_TOLERANCE = 2

# check_rhythm_break_anomaly()'s "unusual hour" branch: how far (in hours, allowing for midnight
# wraparound) a currently-online device's *current* hour may differ from its own
# typical_active_hour before it counts as an unusual-hour deviation.
UNUSUAL_HOUR_TOLERANCE = 4

# check_rhythm_break_anomaly()'s "expected absent" branch: an offline device with a reliable
# baseline is flagged only within this many hours *after* its typical_active_hour -- catches "it
# should be on by now" without nagging forever about a device that's simply been off for days.
EXPECTED_ABSENT_WINDOW_HOURS = 3

# set up logging
logger = logging.getLogger("DaemonLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_random_quip(quip_type: str) -> str:
    """Get a random quip of given type using ID-based selection (avoids ORDER BY RAND())."""
    import random

    db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
    cursor = db.cursor()
    try:
        cursor.execute("SELECT MAX(id) FROM quips WHERE type = %s", (quip_type,))
        max_id_result = cursor.fetchone()
        if not max_id_result or not max_id_result[0]:
            return None
        max_id = max_id_result[0]
        random_id = random.randint(1, max_id)
        cursor.execute(
            "SELECT quips FROM quips WHERE id >= %s AND type = %s LIMIT 1",
            (random_id, quip_type),
        )
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        db.close()


def consume_integrations() -> None:
    """Consume integration messages from Kafka integrations topic."""
    try:
        logger.info(f"Integration consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "integrations", bootstrap_servers=KAFKA_URL, auto_offset_reset="latest"
        )
        logger.info("Connected to Kafka integrations topic")
        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        logger.info("Polling for integration message")
                        try:
                            data = orjson.loads(message.value)
                            if data.get("type") == "calendar" and data.get("action") == "sync":
                                calendar_utils.sync_calendar()
                            elif data.get("type") == "gmail" and data.get("action") == "sync":
                                gmail_utils.sync_gmail()
                        except orjson.JSONDecodeError as e:
                            logger.error(f"Error processing integration message: {str(e)}")
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for integrations: {str(e)}")


class MyDaemon:
    def run(self):
        last_reset_date = None
        while True:
            schedule.run_pending()  # Execute any pending scheduled tasks
            local_today = db_utils.get_env_local_time(ENV_NAME).date()
            if last_reset_date is not None and local_today != last_reset_date:
                reset_routines()
            last_reset_date = local_today
            self.scan_devices()
            self.check_routines()
            if not self.check_mute_status():
                self.perform_waking_hours_tasks()
            try:
                self.check_situational_awareness()
            except Exception as e:
                logger.error("Situational awareness check failed: " + str(e))
            time.sleep(60)

    def be_smart(self) -> None:
        """
        Description:
                 speak a quip
        """
        global QUIP_START_TIME
        global QUIP_WAIT_TIME

        if time.time() - QUIP_START_TIME > QUIP_WAIT_TIME * 60:
            # Unprompted chatter should taper off before bed. be_smart() only
            # runs inside waking hours already (check_mute gates the caller), so
            # the new condition here is the wind-down tail -- the ~45 min before
            # the Bedtime routine. Routine quips and answers to real requests
            # still speak; this timer does not.
            try:
                if day_context.get_day_context(ENV_NAME).in_wind_down:
                    logger.info("Winding down for the night - skipping idle quip")
                    QUIP_START_TIME = time.time()
                    QUIP_WAIT_TIME = randint(10, 50)
                    return
            except Exception as e:
                logger.warning(f"be_smart: day context check failed ({e}); speaking anyway")

            logger.info("It is time to be a smartass")

            quip = get_random_quip("smart")

            p = get_producer()
            if p and quip:
                p.send("speak", quip.encode("utf-8"))

            QUIP_START_TIME = time.time()
            QUIP_WAIT_TIME = randint(10, 50)
            print("Time until next quip: ", QUIP_WAIT_TIME)  # DEBUG

            logger.info("QUIP_START_TIME and QUIP_WAIT_TIME have been reset")
            logger.info("Next quip will be shouted in " + str(QUIP_WAIT_TIME) + " minutes.")

    def play_tune(self):
        """
        Description:
                pick a song or playlist based on current context (people/time/weather)
                and play it via Spotify.
        """
        logger.info("playing a tune")
        try:
            from common import spotify_utils as spotify_api

            if not spotify_api.is_authorized():
                logger.warning("Spotify not authorized — cannot play a tune")
                return

            total_people = 0
            guest_count = 0
            try:
                db = pymysql.connect(
                    host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
                )
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM user WHERE state = 2")
                online = cursor.fetchone()
                total_people = online[0] if online and online[0] else 0
                cursor.execute(
                    "SELECT description, subjective_feel FROM environment WHERE name = %s",
                    (ENV_NAME,),
                )
                desc_row = cursor.fetchone()
                db.close()
                desc, subj = desc_row if desc_row else (None, None)
            except pymysql.Error as e:
                logger.error("play_tune DB error: " + str(e))
                desc, subj = None, None

            local_dt = db_utils.get_env_local_time(ENV_NAME)
            time_of_day = timeofday.coarse_bucket(local_dt.hour)

            reco = spotify_utils.recommend(
                total_people=total_people,
                guest_count=guest_count,
                time_of_day=time_of_day,
                weather={"description": desc, "subjective_feel": subj},
                is_party_night=spotify_utils.is_party_night(local_dt),
            )
            hint = reco.get("playlist_hint") or reco.get("mood") or ""
            logger.info(f"Playing a tune — context: {reco}")

            ok, err = spotify_api.play_recommended(hint)
            if ok:
                logger.info(f"Playing tune: {hint}")
            else:
                logger.warning(f"Could not play tune ({hint}): {err}")
        except Exception as e:
            logger.error(f"play_tune error: {str(e)}")

    def night_light(self):
        """
        Description:
                is anyone at home?
                is it after dark?
                turn the lights on or off as needed.
        """
        logger.info("night_light auto-check")

    def check_mute(self):
        """
        Description:
                checks what time it is and decides if Alfr3d should be quiet
                - between wake-up time and bedtime
                - only when Athos is at home
                - only when 'owner' is at home
        """
        logger.info("Checking if Alfr3d should be muted")
        result = util_routines.check_mute()

        return result

    def check_situational_awareness(self):
        """Poll data and publish array of situational awareness cards."""
        results = self.decide_displays()
        if results:
            self.publish_sa(results)

    # Registry of situational-awareness display rules: (id, priority, check method name).
    # Each check_* method still stamps its own "priority" onto the card it returns;
    # the id/priority here just drive iteration order and logging.
    #
    # SA-5: every card is {mode, content, priority, ...}. `content` is prose and stays
    # authoritative for display -- it's what the `speak`/TTS path and the LLM personality
    # layer consume, and it's the human-readable fallback. `data` (optional -- a rule with
    # nothing worth exposing beyond content and its existing top-level fields just omits it)
    # is the structured facts a consumer would otherwise have to regex out of that prose.
    # Rule of thumb: if a number appears in the prose, it belongs in `data`. Pre-existing
    # top-level extras (entity_name, resume_type/resume_target, playlist_*, switch_count,
    # unlock_count, known_count/unknown_count/urgent, device_count, confidence,
    # conference_uri, track_title/track_artist/is_playing) are unchanged -- SA-5 does not
    # move anything a consumer might already read into `data` retroactively.
    # `data.because` (optional, SA-5 Phase 3): a short list of the signals that caused the
    # rule to fire -- interpretable evidence, not a full audit log.
    #
    # Per-mode `data` schemas (all keys optional/nullable unless noted):
    #   event:                 title, start_time (ISO), minutes_until, because
    #   focus_needed:           title, start_time (ISO), minutes_until, because
    #   music (check_gatherings): mood, genre, energy, tempo_hint, guest_count, total_count,
    #                           time_of_day, because
    #   party_advisory:        track_name, energy, day_of_week, because
    #   weather:                city, subjective_feel, description, low, high
    #   weather_advisory:      forecast_rain_probability, hours_ahead, because
    #   mood:                   day_of_week, time_of_day, energy, energy_label
    #   household_composition: known_names
    #   rhythm_break_anomaly:  varies by deviation_type -- still_on_past_typical:
    #                           over_by_minutes/typical_daily_max_minutes; unusual_hour:
    #                           current_hour/typical_active_hour; expected_absent:
    #                           typical_active_hour; all three also carry because
    #   cross_surface_continuity (music candidate only): minutes_ago
    #   attention_focus:       because
    #   wind_down_signal:      because
    #   empty_house_still_on:  smarthome_device_names, because
    #   departure_anomaly:      typical_departure_hour, sample_count, because
    #   travel:                 duration_minutes, distance_km, traffic_aware, leave_by, because
    #   household_unusual_day:  today_device_count, typical_device_count_range,
    #                           today_first_activity_hour, typical_first_activity_hour, because
    #   time, music (check_now_playing), email, cross_surface_continuity
    #   (terminal/routine candidates): no `data` -- nothing beyond content and existing
    #   top-level fields is currently hidden in the prose for these.
    DISPLAY_RULES = (
        ("time", 1, "check_time"),
        ("event", 2, "check_events"),
        # SA-6: restores what commit 08509ce removed, on self-hosted infrastructure. Between
        # event (2) and empty_house_still_on (2.4)/rhythm_break_anomaly (2.6) -- an orchestrating,
        # time-boxed card, matching its original placement before removal.
        ("travel", 2.5, "check_travel"),
        ("music", 3, "check_gatherings"),
        # What's actually playing right now, independent of whether a
        # gathering triggered a recommendation -- priority 3.1 keeps it
        # right after the recommendation card it complements, ahead of the
        # party advisory (3.2) that reacts to this same playback state.
        ("now_playing", 3.1, "check_now_playing"),
        # Follows directly on from music (3): checks whether what's actually
        # playing is genuinely high-energy despite a capped weeknight
        # recommendation. Priority 3.2 keeps it right after the card it's
        # reacting to, ahead of focus_needed (3.5).
        ("party_advisory", 3.2, "check_party_advisory"),
        # A call starting soon is more actionable/time-boxed than the ambient
        # "should I play music" gathering check, but not as centrally
        # orchestrating as an event departure — priority 3.5 sits it directly
        # between music (3) and email (4) without renumbering existing rules.
        ("focus_needed", 3.5, "check_focus_needed"),
        # Evidence-based sibling to focus_needed, not a replacement -- see
        # check_attention_focus()'s own doc comment.
        ("attention_focus", 3.6, "check_attention_focus"),
        ("email", 4, "check_emails"),
        # Forward-looking and actionable ("bring an umbrella"), unlike the
        # passive weather status readout below it -- sits between email (4)
        # and weather (5) the same way focus_needed sits between music and
        # email.
        ("weather_advisory", 4.5, "check_weather_advisory"),
        ("weather", 5, "check_weather"),
        # mood is lower-urgency ambient context, not an actionable alert —
        # slotted just below weather rather than competing with priorities 1-5.
        ("mood", 6, "check_mood"),
        # Priority isn't fixed here -- check_household_composition() computes it per-call:
        # ambient (6.2, next to mood) when every online device is claimed, elevated (2.3,
        # next to event/gathering) when an unclaimed/unknown device is on the network.
        ("household_composition", 6.2, "check_household_composition"),
        # Actionable, near event/gathering: a genuine deviation from a device's
        # established on/off rhythm is worth surfacing promptly.
        ("rhythm_break_anomaly", 2.6, "check_rhythm_break_anomaly"),
        # SA-3: the human analogue of rhythm_break_anomaly, one priority tier below it --
        # "usually gone by now, still home" is a genuine routine deviation, not an alert.
        ("departure_anomaly", 2.7, "check_departure_anomaly"),
        # Helpful, not urgent -- below weather (5), above mood (6.2/2.3): a
        # convenience "resume" offer, not something demanding attention.
        ("cross_surface_continuity", 5.5, "check_cross_surface_continuity"),
        # Just below cross_surface_continuity -- a low-urgency suggestion,
        # not something demanding attention either.
        ("wind_down_signal", 5.8, "check_wind_down_signal"),
        # SA-4 Phase 3 proof case: needs three frame fields at once
        # (online_devices, smarthome_online, day_mood) and couldn't have been
        # written before the context frame existed. Near rhythm_break_anomaly
        # (2.6) and household_composition's elevated variant (2.3) -- worth
        # attention, not an emergency.
        ("empty_house_still_on", 2.4, "check_empty_house_still_on"),
        # SA-10 Phase 3: household-level analogue of departure_anomaly/rhythm_break_anomaly --
        # just below mood (6)/household_composition's ambient variant (6.2), an observation, not
        # an alert. At most one card per day by construction (gated on being past the day's
        # typical_last_activity_hour).
        ("household_unusual_day", 6.5, "check_household_unusual_day"),
    )

    # Cap on cards published per cycle. Tied to the number of registered rules so
    # that every currently-registered category can coexist — previously a hardcoded
    # [:4] slice silently dropped weather (priority 5) whenever all five checks
    # fired. Grows automatically if DISPLAY_RULES grows, so adding a rule doesn't
    # silently reintroduce the same drop.
    MAX_DISPLAYS = len(DISPLAY_RULES)

    def build_context_frame(self):
        """Assemble one context_frame.ContextFrame for this decide_displays() cycle (SA-4).

        Each field is fetched in its own try/except -- one integration failing (Spotify
        unreachable, a query erroring) must not prevent unrelated fields, or the cards that
        depend on them, from being built. See context_frame.py's module docstring for the
        exact duplicate DB/API calls this eliminates.
        """
        frame = context_frame.ContextFrame()
        frame.now = datetime.now(timezone.utc)

        try:
            frame.local_dt = db_utils.get_env_local_time(ENV_NAME)
            frame.day_mood = mood_utils.get_day_mood(frame.local_dt)
            frame.day_ctx = day_context.get_day_context(ENV_NAME, now=frame.local_dt)
        except Exception as e:
            logger.error(f"Context frame: day_mood build failed: {e}")

        try:
            frame.upcoming_events = calendar_utils.get_upcoming_events()
        except Exception as e:
            logger.error(f"Context frame: upcoming_events build failed: {e}")

        try:
            frame.online_devices = context_frame.fetch_online_devices()
        except Exception as e:
            logger.error(f"Context frame: online_devices build failed: {e}")

        try:
            frame.smarthome_online = context_frame.fetch_smarthome_online()
        except Exception as e:
            logger.error(f"Context frame: smarthome_online build failed: {e}")

        try:
            frame.environment = context_frame.fetch_environment_snapshot(ENV_NAME)
        except Exception as e:
            logger.error(f"Context frame: environment build failed: {e}")

        try:
            from common import spotify_utils as spotify_api

            frame.playback = spotify_api.get_playback_state()
        except Exception as e:
            logger.error(f"Context frame: playback build failed: {e}")

        try:
            frame.persisted_now_playing = self._read_config_json(NOW_PLAYING_CONFIG_KEY)
        except Exception as e:
            logger.error(f"Context frame: persisted_now_playing build failed: {e}")

        try:
            launcher = context_frame.LauncherContext()
            launcher.surface_state = self._read_config_json(SURFACE_STATE_CONFIG_KEY)
            launcher.attention_snapshot = self._read_fresh_attention_telemetry()
            launcher.attention_trend = self._attention_telemetry_trend()
            frame.launcher_context = launcher
        except Exception as e:
            logger.error(f"Context frame: launcher_context build failed: {e}")

        return frame

    def decide_displays(self):
        """Run every registered display rule and return non-None cards, sorted by priority.

        Builds one context_frame.ContextFrame (SA-4) at the top of the cycle and passes it to
        every check -- see build_context_frame()'s docstring. A card whose rule doesn't use any
        frame field still receives it, for consistency and so it shares `frame.now` with every
        other card this cycle.

        A suppression pass (SA-1) runs after collection, before the sort: a card whose
        identity was recently dismissed, or has repeated too many cycles running with no
        interaction at all, is dropped -- unless its `urgent` field opts it out entirely
        (see CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD; household_composition's elevated
        variant is the only rule using this today).
        """
        frame = self.build_context_frame()
        collected = []
        for rule_id, _priority, check_name in self.DISPLAY_RULES:
            logger.info(f"Collecting displays: checking {rule_id}")
            card = getattr(self, check_name)(frame)
            if card:
                collected.append((rule_id, card))

        displays = []
        for rule_id, card in collected:
            # Stamp the card's own identity onto it so consumers (React dashboard, Nexus
            # Launcher) can report shown/tapped/dismissed against the same (rule_id,
            # subject_key) this suppression pass uses -- without this, a consumer would
            # have no reliable way to identify a card (the card's own "mode" field
            # collides across rules; see CARD_SUBJECT_KEY_EXTRACTORS' own comment).
            subject_key = self._card_subject_key(rule_id, card)
            card["rule_id"] = rule_id
            card["subject_key"] = subject_key
            if card.get(CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD):
                displays.append(card)
                continue
            reason = self._card_suppression_reason(rule_id, subject_key)
            if reason:
                logger.info(f"Suppressing {rule_id} card (subject={subject_key!r}): {reason}")
                continue
            displays.append(card)

        if not displays:
            logger.info("No priority displays, defaulting to time and weather")

        logger.debug("Displays before sorting: " + str(displays))
        # sort by priority
        displays.sort(key=lambda x: x["priority"])

        logger.debug("Final displays selected: " + str(displays))
        return displays[: self.MAX_DISPLAYS]

    @staticmethod
    def _card_subject_key(rule_id, card):
        """Subject-key half of a card's (rule_id, subject_key) identity (SA-1) -- ""
        for the (majority of) rules with no per-entity extractor registered in
        CARD_SUBJECT_KEY_EXTRACTORS, meaning the whole rule is one suppressible slot."""
        extractor = CARD_SUBJECT_KEY_EXTRACTORS.get(rule_id)
        return extractor(card) if extractor else ""

    def _card_suppression_reason(self, rule_id, subject_key):
        """Return a short reason string to suppress this (rule_id, subject_key) card
        identity, or None to show it as normal. Reads card_interactions only -- the
        daemon never writes to it, only consumers report shown/tapped/dismissed/expired
        (see routes/context.py's POST /api/context/card-interaction); a published card
        that never made it past a client's own display cap was never actually "shown",
        and the daemon has no way to know that, so it must not assume otherwise."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT action, occurred_at FROM card_interactions "
                "WHERE rule_id = %s AND subject_key = %s ORDER BY occurred_at DESC LIMIT %s",
                (rule_id, subject_key, CARD_SUPPRESSION_HISTORY_LIMIT),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            latest_action, latest_at = rows[0]
            if latest_action == "dismissed":
                cooldown = CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.get(
                    rule_id, CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES
                )
                since = datetime.now(timezone.utc) - latest_at.replace(tzinfo=timezone.utc)
                if since < timedelta(minutes=cooldown):
                    return "cooldown"
                return None

            run_length = 0
            for action, _ in rows:
                if action != "shown":
                    break
                run_length += 1
            threshold = CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.get(
                rule_id, CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES
            )
            if run_length >= threshold:
                return "repetition"
            return None
        except pymysql.Error as e:
            logger.error(f"Card suppression check error: {e}")
            return None
        finally:
            if db:
                db.close()

    def check_emails(self, frame=None):
        """Check for unread emails using Gmail utils. Not a frame field (SA-4) -- not
        duplicated by any other rule, so its own direct Gmail call stays as-is.
        `frame` defaults to None (unused) because perform_waking_hours_tasks() also
        calls this directly, outside decide_displays()'s per-cycle frame, for its own
        separate "check Gmail" waking-hours routine."""
        del frame
        emails = gmail_utils.check_unread_emails()
        if emails:
            email = emails[0]  # Take first
            content_lines = f"From: {email['sender']}, Subject: {email['subject']}"
            content = f"Unread Email - {content_lines} | Total Unread: {len(emails)}"
            return {"mode": "email", "content": content, "priority": 4}

    def check_events(self, frame):
        """Check for upcoming events, showing plain title/time info.

        `frame.upcoming_events` (SA-4) replaces this rule's own
        calendar_utils.get_upcoming_events() call -- check_focus_needed() reads the exact same
        query, so both now share the one fetch build_context_frame() makes per cycle.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]  # Take first
        if event["start_time"] - frame.now > timedelta(hours=3):
            return None  # Only care about events within next hour
        title = event["title"]
        start_time = event["start_time"]
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        content = f"Upcoming event: {title} at {start_time.strftime('%I:%M %p')}"
        return {
            "mode": "event",
            "content": content,
            "priority": 2,
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": [f"{title} starts in {minutes_until} min"],
            },
        }

    def check_travel(self, frame):
        """SA-6: restores what commit 08509ce removed (Google Maps Directions-based
        check_travel()), on self-hosted infrastructure -- see
        todo/todo_self_hosted_routing.md for the Phase 0 spike that justified self-hosted OSRM
        for routing (measured live against real production hardware) plus the public Nominatim
        API for the much rarer geocoding need, over any paid/hosted alternative.

        Fires only when the next calendar event has a resolvable physical destination -- a
        non-empty `address` and no `conference_uri` (a video call has nowhere to drive to; that
        case is check_focus_needed()'s job, not this one's) -- and the computed leave-by time
        falls within TRAVEL_LEAD_MINUTES of frame.now, in either direction.

        Fails closed and silent at every step: an ungeocodable address, a household location
        that hasn't been geocoded yet, or an unreachable routing container all mean no card,
        never a fabricated estimate -- the exact anti-pattern the original implementation was
        criticized for. `data.traffic_aware` is always `false`: none of the self-hosted routing
        engines evaluated match Google's live-traffic layer, so no consumer should present this
        as anything but a free-flow/typical-conditions estimate.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        address = (event.get("address") or "").strip()
        if not address or event.get("conference_uri"):
            return None
        start_time = event.get("start_time")
        if start_time is None or frame.now is None:
            return None

        dest = routing_utils.geocode_address(address)
        if dest is None:
            return None
        origin = routing_utils.fetch_home_coordinates(ENV_NAME)
        if origin is None:
            return None
        route = routing_utils.get_route(origin, dest)
        if route is None:
            return None

        leave_by = start_time - timedelta(minutes=route["duration_minutes"])
        minutes_until_leave = (leave_by - frame.now).total_seconds() / 60
        if abs(minutes_until_leave) > TRAVEL_LEAD_MINUTES:
            return None

        title = event["title"]
        duration_minutes = round(route["duration_minutes"])
        distance_km = round(route["distance_km"], 1)
        content = f"Leave by {leave_by.strftime('%I:%M %p')} for {title}"
        return {
            "mode": "travel",
            "content": content,
            "priority": 2.5,
            "data": {
                "duration_minutes": duration_minutes,
                "distance_km": distance_km,
                "traffic_aware": False,
                "leave_by": leave_by.isoformat(),
                "because": [f"{duration_minutes} min drive to {title}"],
            },
        }

    def check_focus_needed(self, frame):
        """Check whether the next upcoming event looks like a call starting soon.

        Reuses `frame.upcoming_events` (SA-4; same source check_events() reads) and applies
        focus_utils.looks_like_call() (SA-7) -- tiered by confidence: `focus_utils.CONFIRMED`
        when the event carries real synced conferencing data (`conference_uri`),
        `focus_utils.PROBABLE` when only the text heuristic over address/notes matches. See
        focus_utils' module docstring for the full tier breakdown and known false-positive
        shape of the probable tier. Only fires within FOCUS_LEAD_MINUTES of the event's start.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        confidence = focus_utils.looks_like_call(
            event["address"], event["notes"], event.get("conference_uri")
        )
        if not confidence:
            return None
        start_time = event["start_time"]
        if start_time - frame.now > timedelta(minutes=FOCUS_LEAD_MINUTES):
            return None
        title = event["title"]
        if confidence == focus_utils.CONFIRMED:
            solution = event.get("conference_solution") or "Call"
            content = (
                f"{solution} starting soon: {title} at {start_time.strftime('%I:%M %p')}. "
                "Find a quiet spot."
            )
        else:
            content = (
                f"Looks like a call starting soon: {title} at {start_time.strftime('%I:%M %p')}. "
                "Find a quiet spot."
            )
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        return {
            "mode": "focus_needed",
            "content": content,
            "priority": 3.5,
            "confidence": confidence,
            "conference_uri": event.get("conference_uri"),
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": [
                    f"{title} starts in {minutes_until} min",
                    (
                        "confirmed conferencing data"
                        if confidence == focus_utils.CONFIRMED
                        else "text looks like a call"
                    ),
                ],
            },
        }

    def check_gatherings(self, frame):
        """Check for gatherings (>3 guests/residents online).

        `frame.local_dt`/`frame.day_mood` (SA-4) replace this rule's own
        db_utils.get_env_local_time()/mood_utils.get_day_mood() calls -- check_party_advisory(),
        check_wind_down_signal(), and check_mood() all needed the exact same pair. `frame.
        environment`'s description/subjective_feel replace this rule's own separate read of the
        same `environment` row check_weather()/check_weather_advisory() also read.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN ut.type IN ('guest') THEN 1 ELSE 0 END) as guest_count,
                    COUNT(*) as total_count
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                WHERE s.state = 'online' AND u.username != 'unknown'
                """
            )
            row = cursor.fetchone()
            # SUM() returns decimal.Decimal via pymysql (unlike COUNT()'s plain int) -- cast
            # so guest_count is safe to embed directly in the "data" dict's JSON payload (SA-5),
            # not just interpolated into f-string content like before.
            guest_count = int(row[0]) if row and row[0] else 0
            total_count = int(row[1]) if row and row[1] else 0

            if guest_count > 0:
                logger.info(
                    "Gathering detected with total people: "
                    + str(total_count)
                    + " (guests: "
                    + str(guest_count)
                    + ")"
                )
                if frame.local_dt is None or frame.day_mood is None:
                    return None
                local_dt = frame.local_dt
                time_of_day = frame.day_mood["time_of_day"]
                environment = frame.environment or {}
                weather_info = {
                    "description": environment.get("description"),
                    "subjective_feel": environment.get("subjective_feel"),
                }

                reco = spotify_utils.recommend(
                    total_people=total_count,
                    guest_count=guest_count,
                    time_of_day=time_of_day,
                    weather=weather_info,
                    is_party_night=spotify_utils.is_party_night(local_dt),
                )
                logger.info(f"Recommendation: {reco}")

                p = get_producer()
                if p:
                    event = {
                        "id": f"gathering_detected_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "type": "info",
                        "message": (
                            f"Gathering detected with {total_count} people "
                            f"({guest_count} guests). Suggesting {reco['mood']} music "
                            f"({reco['genre']})."
                        ),
                        "time": datetime.now(timezone.utc).isoformat(),
                    }
                    p.send("event-stream", orjson.dumps(event))

                hint = reco.get("playlist_hint", reco.get("mood", ""))
                playlist = None
                try:
                    playlist = spotify_utils.resolve_playlist(hint, reco.get("genre", ""))
                except Exception as e:
                    logger.warning(f"Playlist resolution failed, using text hint only: {e}")

                display_name = playlist.get("name") if playlist else hint
                content = f"Play {display_name} ({reco['genre']}, energy={reco['energy']})"
                card = {
                    "mode": "music",
                    "content": content,
                    "priority": 3,
                    "data": {
                        "mood": reco.get("mood"),
                        "genre": reco.get("genre"),
                        "energy": reco.get("energy"),
                        "tempo_hint": reco.get("tempo_hint"),
                        "guest_count": guest_count,
                        "total_count": total_count,
                        "time_of_day": time_of_day,
                        "because": [
                            f"{guest_count} guest(s) online",
                            f"{time_of_day} time of day",
                        ],
                    },
                }
                if playlist:
                    card.update(
                        {
                            "playlist_id": playlist.get("id"),
                            "playlist_name": playlist.get("name"),
                            "playlist_uri": playlist.get("uri"),
                            "playlist_url": playlist.get("url"),
                            "playlist_image": playlist.get("image"),
                            "playlist_source": playlist.get("source"),
                        }
                    )
                return card
            return None
        except pymysql.Error as e:
            logger.error("Gathering check error: " + str(e))
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()

    def check_household_composition(self, frame):
        """Report which household members' claimed devices are online right now, vs. how
        many unclaimed/unknown MACs are also on the network.

        `device.user_id` is already exactly "this MAC is claimed by a household member" --
        the arp-scan sync (service_device.app.check_lan/update_or_create_device) never sets
        it on discovery, only the device-management UI does -- so no new table is needed to
        tell known from unknown. Priority is computed here rather than fixed in DISPLAY_RULES:
        ambient (6.2) when everything online is claimed, elevated (2.3, security-relevant)
        when at least one unclaimed device is online.

        `frame.online_devices` (SA-4) replaces this rule's own device/state/user query --
        the same fetch check_empty_house_still_on() also reads.
        """
        online = frame.online_devices
        if not online or not online["rows"]:
            return None

        known_names = online["known_names"]
        known_count = online["known_count"]
        unknown_count = online["unknown_count"]

        if unknown_count > 0:
            content = f"{unknown_count} unrecognized device(s) on the network" + (
                f" alongside {', '.join(known_names)}" if known_names else ""
            )
            return {
                "mode": "household_composition",
                "content": content,
                "priority": 2.3,
                "known_count": known_count,
                "unknown_count": unknown_count,
                "urgent": True,
                "data": {"known_names": known_names},
            }

        content = f"Home: {', '.join(known_names)}" if known_names else "No known devices online"
        return {
            "mode": "household_composition",
            "content": content,
            "priority": 6.2,
            "known_count": known_count,
            "unknown_count": unknown_count,
            "urgent": False,
            "data": {"known_names": known_names},
        }

    def check_empty_house_still_on(self, frame):
        """No claimed household member's device is online, but at least one smart-home
        device still is -- the SA-4 Phase 3 proof case: a rule that genuinely could not have
        been written before the context frame existed, since it needs `frame.online_devices`
        (is anyone actually home), `frame.smarthome_online` (what's still running), and
        `frame.day_mood` (only worth a nudge once it's evening/night -- during the day
        "everyone's out, the office lamp is on" is unremarkable, not everyone being home all
        day is normal) all at once. Observation only, like every other card in this file --
        it names what's still on, it does not turn anything off.
        """
        online = frame.online_devices
        smarthome_online = frame.smarthome_online
        if online is None or online["known_count"] > 0:
            return None
        if not smarthome_online:
            return None
        if frame.day_mood is None or frame.day_mood["time_of_day"] not in ("evening", "night"):
            return None
        content = f"House appears empty, but {', '.join(smarthome_online)} still on"
        return {
            "mode": "empty_house_still_on",
            "content": content,
            "priority": 2.4,
            "device_count": len(smarthome_online),
            "data": {
                "smarthome_device_names": smarthome_online,
                "because": [
                    "no claimed household device online",
                    f"{frame.day_mood['time_of_day']}",
                ],
            },
        }

    def check_rhythm_break_anomaly(self, frame):
        """Compare devices against their `entity_baselines` row and surface a card only on a
        genuine deviation from routine. Three deviation types, checked in this order (the first
        one that fires wins -- still one card per cycle, same "one card per check" shape as every
        other DISPLAY_RULES method):

        1. `still_on_past_typical` (original): a currently-online device has been on
           RHYTHM_BREAK_GRACE_MINUTES+ past its typical_daily_max for this session.
        2. `unusual_hour` (SA-10): a currently-online device's *current* hour is
           UNUSUAL_HOUR_TOLERANCE+ hours away from its typical_active_hour (circular distance,
           so 23:00 vs. a typical_active_hour of 1 counts as 2 hours apart, not 22).
        3. `expected_absent` (SA-10): a currently-*offline* device is still absent within
           EXPECTED_ABSENT_WINDOW_HOURS of its typical_active_hour -- "it should be on by now."
           Known limitation: doesn't handle a typical_active_hour that wraps past midnight (e.g.
           23 + a 3-hour window) -- narrow edge case, not worth the extra query complexity this
           pass; documented here rather than silently wrong.

        All three require `eb.sample_count >= eb.min_sample_count` explicitly (SA-10's
        min_sample_count column) rather than trusting every row in the table implicitly --
        today every row already cleared its floor at write time, but this is the same "do I
        trust this yet" check every consumer should make, not just the ones that happen to need
        it right now.

        Not a frame field (SA-4) -- this device/entity_baselines join isn't duplicated by any
        other rule, so it stays its own query; only `frame.now` (SA-4's single
        shared-per-cycle timestamp) replaces this rule's own datetime.now(timezone.utc) call.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            now = frame.now

            cursor.execute(
                """
                SELECT d.name, TIMESTAMPDIFF(MINUTE, d.last_online, %s) AS minutes_on,
                       eb.typical_daily_max
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'online'
                  AND d.last_online IS NOT NULL
                  AND eb.typical_daily_max IS NOT NULL
                  AND eb.sample_count >= eb.min_sample_count
                  AND TIMESTAMPDIFF(MINUTE, d.last_online, %s) > eb.typical_daily_max + %s
                ORDER BY (TIMESTAMPDIFF(MINUTE, d.last_online, %s) - eb.typical_daily_max) DESC
                LIMIT 1
                """,
                (now, now, RHYTHM_BREAK_GRACE_MINUTES, now),
            )
            row = cursor.fetchone()
            if row:
                name, minutes_on, typical_max = row
                over_by = int(minutes_on - typical_max)
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} has been on for {over_by} min longer than usual",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "still_on_past_typical",
                    "data": {
                        "over_by_minutes": over_by,
                        "typical_daily_max_minutes": int(typical_max),
                        "because": [
                            f"on {over_by} min past its typical max ({int(typical_max)} min)"
                        ],
                    },
                }

            cursor.execute(
                """
                SELECT d.name, HOUR(%s) AS current_hour, eb.typical_active_hour,
                       LEAST(
                           ABS(HOUR(%s) - eb.typical_active_hour),
                           24 - ABS(HOUR(%s) - eb.typical_active_hour)
                       ) AS hour_distance
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'online'
                  AND eb.typical_active_hour IS NOT NULL
                  AND eb.sample_count >= eb.min_sample_count
                HAVING hour_distance > %s
                ORDER BY hour_distance DESC
                LIMIT 1
                """,
                (now, now, now, UNUSUAL_HOUR_TOLERANCE),
            )
            row = cursor.fetchone()
            if row:
                name, current_hour, typical_hour, hour_distance = row
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} is on at an unusual hour",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "unusual_hour",
                    "data": {
                        "current_hour": int(current_hour),
                        "typical_active_hour": int(typical_hour),
                        "because": [
                            f"on at {int(current_hour):02d}:00, typically active around "
                            f"{int(typical_hour):02d}:00"
                        ],
                    },
                }

            cursor.execute(
                """
                SELECT d.name, HOUR(%s) AS current_hour, eb.typical_active_hour
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'offline'
                  AND eb.typical_active_hour IS NOT NULL
                  AND eb.sample_count >= eb.min_sample_count
                  AND HOUR(%s) >= eb.typical_active_hour
                  AND HOUR(%s) < eb.typical_active_hour + %s
                ORDER BY (HOUR(%s) - eb.typical_active_hour) DESC
                LIMIT 1
                """,
                (now, now, now, EXPECTED_ABSENT_WINDOW_HOURS, now),
            )
            row = cursor.fetchone()
            if row:
                name, current_hour, typical_hour = row
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} hasn't come online yet",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "expected_absent",
                    "data": {
                        "typical_active_hour": int(typical_hour),
                        "because": [
                            f"usually active by {int(typical_hour):02d}:00, "
                            f"still offline at {int(current_hour):02d}:00"
                        ],
                    },
                }

            return None
        except pymysql.Error as e:
            logger.error("Rhythm break anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

    def check_departure_anomaly(self, frame):
        """SA-3: "usually gone by now, still home" -- the human analogue of
        check_rhythm_break_anomaly(), reading compute_entity_baselines()'s `entity_type='user'`
        rows instead of `'device'`. See todo/todo_departure_anomaly.md for the Phase 0 spike that
        justified deriving this from the existing device_history/entity_baselines pattern rather
        than a new table.

        Fires only when every one of these holds, for at least one resident:
        - a reliable baseline exists for today's weekday/weekend bucket (sample-count floor
          *and* a tight-enough observed hour spread -- DEPARTURE_BASELINE_MIN_SAMPLES/
          DEPARTURE_BASELINE_MAX_SPREAD_HOURS; a resident whose real departure times are just
          scattered gets no baseline at all rather than a noisy one),
        - the local hour is past that baseline's typical departure hour, plus a grace window
          (DEPARTURE_ANOMALY_GRACE_HOURS) so running a bit late isn't an anomaly,
        - at least one of that resident's claimed devices is online right now,
        - and no household calendar event covers this exact moment (a booked morning at home,
          e.g. WFH, is not a deviation -- checked directly against calendar_events, not
          frame.upcoming_events, which only looks a couple hours *forward* and would miss an
          event already in progress).

        Only one card per cycle, same "single most-overdue" precedent as
        check_rhythm_break_anomaly() -- picks the resident furthest past their typical hour.

        Tone constraint (from the task doc): this is an ambient observation, never a welfare
        check. "Still home -- unusual for a Tuesday," never "is everything okay?"
        """
        if frame.local_dt is None or frame.day_mood is None:
            return None
        local_dt = frame.local_dt
        day_bucket = "weekend" if local_dt.weekday() >= 5 else "weekday"
        current_hour = local_dt.hour + local_dt.minute / 60

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT eb.entity_id, u.username, eb.typical_active_hour, eb.sample_count
                FROM entity_baselines eb
                JOIN user u ON u.id = eb.entity_id
                JOIN user_types ut ON u.type = ut.id
                WHERE eb.entity_type = 'user' AND eb.day_bucket = %s
                  AND eb.sample_count >= %s
                  AND (eb.typical_daily_max - eb.typical_daily_min) <= %s
                  AND ut.type IN ('owner', 'technoking', 'resident')
                """,
                (day_bucket, DEPARTURE_BASELINE_MIN_SAMPLES, DEPARTURE_BASELINE_MAX_SPREAD_HOURS),
            )
            candidates = cursor.fetchall()
            if not candidates:
                return None

            overdue = []
            for user_id, username, typical_hour, sample_count in candidates:
                if current_hour < typical_hour + DEPARTURE_ANOMALY_GRACE_HOURS:
                    continue
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM device d
                    JOIN states s ON d.state = s.id
                    WHERE d.user_id = %s AND s.state = 'online'
                    """,
                    (user_id,),
                )
                (online_count,) = cursor.fetchone()
                if online_count == 0:
                    continue
                overdue.append((current_hour - typical_hour, username, typical_hour, sample_count))

            if not overdue:
                return None

            cursor.execute(
                "SELECT 1 FROM calendar_events WHERE start_time <= %s AND end_time >= %s LIMIT 1",
                (frame.now, frame.now),
            )
            if cursor.fetchone():
                return None

            overdue.sort(reverse=True)
            _over_by, username, typical_hour, sample_count = overdue[0]
            day_of_week = frame.day_mood["day_of_week"]
            return {
                "mode": "departure_anomaly",
                "content": f"{username} still home — unusual for a {day_of_week}",
                "priority": 2.7,
                "entity_name": username,
                "data": {
                    "typical_departure_hour": int(typical_hour),
                    "sample_count": sample_count,
                    "because": [
                        f"usually gone by {int(typical_hour):02d}:00 on a {day_bucket}",
                        f"{sample_count} samples in the last "
                        f"{DEPARTURE_BASELINE_LOOKBACK_DAYS} days",
                    ],
                },
            }
        except pymysql.Error as e:
            logger.error("Departure anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

    def check_household_unusual_day(self, frame):
        """SA-10 Phase 3: "is today unusual for this household" -- the household-level analogue
        of check_rhythm_break_anomaly()/check_departure_anomaly(), reading
        compute_entity_baselines()'s `entity_type='household'` rows. See
        todo/todo_generalize_entity_baselines.md for the Phase 0 investigation (including real
        production-hardware timing) behind generalising entity_baselines rather than adding a
        parallel table.

        Fires only late enough in the day that "today" has had a real chance to look normal --
        past the household's own typical_last_activity_hour for today's bucket, so this can only
        ever produce one card per day (there's no repeat-earlier-in-the-day path) -- and only on
        a genuinely STRONG, multi-signal deviation: BOTH the device-count range and the
        first-activity hour must be off, not just one. A single noisy metric is normal day-to-day
        variance, not "today is different"; the task's own tone constraint (an observation, never
        a concern) is easier to earn when the bar to fire is this high.

        Uses ALL of today's device_history activity (every device, not just claimed ones) --
        household-level "is the house awake" is a broader question than SA-3's per-resident
        departure signal, and an unclaimed smart-home device's own schedule is still real
        evidence of household rhythm.
        """
        if frame.local_dt is None or frame.day_mood is None or frame.now is None:
            return None
        local_dt = frame.local_dt
        day_bucket = "weekend" if local_dt.weekday() >= 5 else "weekday"

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT typical_active_hour, typical_last_activity_hour, typical_daily_min,
                       typical_daily_max, sample_count, min_sample_count
                FROM entity_baselines
                WHERE entity_type = 'household' AND entity_id = %s AND day_bucket = %s
                """,
                (HOUSEHOLD_BASELINE_ENTITY_ID, day_bucket),
            )
            row = cursor.fetchone()
            if not row:
                return None
            (
                typical_first_hour,
                typical_last_hour,
                typical_min,
                typical_max,
                sample_count,
                min_sample_count,
            ) = row
            if sample_count < min_sample_count:
                return None
            if typical_last_hour is None or local_dt.hour < typical_last_hour:
                return None

            # Local midnight, expressed on frame.now's UTC timeline -- local_dt and frame.now
            # differ by a constant offset, so subtracting local_dt's own time-of-day from it
            # lands exactly on local midnight without a separate timezone lookup.
            midnight_utc = frame.now - timedelta(
                hours=local_dt.hour,
                minutes=local_dt.minute,
                seconds=local_dt.second,
                microseconds=local_dt.microsecond,
            )
            cursor.execute(
                "SELECT HOUR(MIN(timestamp)), COUNT(DISTINCT device_id) "
                "FROM device_history WHERE timestamp >= %s",
                (midnight_utc,),
            )
            today_first_hour, today_device_count = cursor.fetchone()
            if today_first_hour is None:
                return None

            count_deviates = today_device_count < typical_min or today_device_count > typical_max
            hour_deviates = (
                abs(today_first_hour - typical_first_hour) > HOUSEHOLD_FIRST_ACTIVITY_HOUR_TOLERANCE
            )
            if not (count_deviates and hour_deviates):
                return None

            day_of_week = frame.day_mood["day_of_week"]
            return {
                "mode": "household_unusual_day",
                "content": f"{day_of_week} is running differently than usual",
                "priority": 6.5,
                "data": {
                    "today_device_count": today_device_count,
                    "typical_device_count_range": [typical_min, typical_max],
                    "today_first_activity_hour": today_first_hour,
                    "typical_first_activity_hour": int(typical_first_hour),
                    "because": [
                        f"{today_device_count} devices active today, "
                        f"typically {int(typical_min)}-{int(typical_max)}",
                        f"first activity at {today_first_hour:02d}:00, "
                        f"typically around {int(typical_first_hour):02d}:00",
                    ],
                },
            }
        except pymysql.Error as e:
            logger.error("Household unusual day check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

    def _read_config_json(self, key):
        """Return the JSON value stored under `config.name = key` as a dict,
        or {} if there is none yet or the read fails. Generalized from what
        was originally `_read_now_playing_config()` -- now also used by
        check_cross_surface_continuity() to read SURFACE_STATE_CONFIG_KEY,
        the launcher-reported surface state written by
        `POST /api/context/surface-state` (service_api/routes/context.py)."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute("SELECT value FROM config WHERE name = %s", (key,))
            row = cursor.fetchone()
            return orjson.loads(row[0]) if row and row[0] else {}
        except Exception as e:
            logger.error(f"Config JSON read error ({key}): {e}")
            return {}
        finally:
            if db:
                db.close()

    def _write_now_playing_config(self, state):
        """Upsert the now-playing state into `config`, following the same
        UPDATE-then-INSERT-if-0-rows pattern used elsewhere for this table
        (e.g. spotify_utils.save_spotify_credentials())."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            value = orjson.dumps(state).decode("utf-8")
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = %s",
                (value, NOW_PLAYING_CONFIG_KEY),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES (%s, %s)",
                    (NOW_PLAYING_CONFIG_KEY, value),
                )
            db.commit()
        except Exception as e:
            logger.error(f"Now playing config write error: {e}")
        finally:
            if db:
                db.close()

    def check_now_playing(self, frame):
        """Surface a situational-awareness card for whatever's actually
        playing on Spotify right now, independent of check_gatherings()'s
        recommendation card.

        Runs every ~60s cycle like every other DISPLAY_RULES check (no
        separate poll loop -- the daemon's outer loop only ticks that often
        anyway). Only persists to `config` and publishes an event-stream
        message when the track or play state actually changed, so it
        doesn't repeat the same "now playing" line every cycle.

        Persists on a play->pause transition too (not just track changes),
        even though no card is returned for the paused state itself --
        check_cross_surface_continuity() needs that persisted "paused N
        minutes ago" state to offer a resume. Before that feature existed,
        pausing never got persisted at all here.

        `frame.playback` (SA-4) replaces this rule's own
        spotify_api.get_playback_state() call -- check_party_advisory() reads the exact same
        fetch. `frame.persisted_now_playing` replaces reading NOW_PLAYING_CONFIG_KEY here --
        check_cross_surface_continuity() reads that same config row too.
        """
        try:
            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            is_playing = state.get("is_playing", False)
            if not track_id:
                return None

            # config.value is VARCHAR(512) -- cap title/artist defensively
            # (no album art is stored here; that's re-fetched live from
            # GET /api/music/spotify/status when needed).
            title = (item.get("name") or "")[:150]
            artist = ", ".join(item.get("artists") or [])[:150]

            last = frame.persisted_now_playing or {}
            if last.get("track_id") != track_id or last.get("is_playing") != is_playing:
                self._write_now_playing_config(
                    {
                        "track_id": track_id,
                        "title": title,
                        "artist": artist,
                        "is_playing": is_playing,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if is_playing:
                    p = get_producer()
                    if p:
                        message = (
                            f"Now playing: {title} by {artist}"
                            if artist
                            else f"Now playing: {title}"
                        )
                        event = {
                            "id": f"now_playing_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "type": "audio",
                            "message": message,
                            "time": datetime.now(timezone.utc).isoformat(),
                            "subject_type": "track",
                            "subject_id": track_id,
                            "verb": "play_start",
                        }
                        p.send("event-stream", orjson.dumps(event))

            if not is_playing:
                return None

            content = f"{title} — {artist}" if artist else title
            return {
                "mode": "music",
                "content": f"Now playing: {content}",
                "priority": 3.1,
                "track_title": title,
                "track_artist": artist,
                "is_playing": is_playing,
            }
        except Exception as e:
            logger.error(f"Now playing check error: {e}")
            return None

    def check_cross_surface_continuity(self, frame):
        """Offer a "pick up where you left off" resume for whichever surface
        was most recently left active: paused Spotify playback, an edited
        Matrix routine, or a reported launcher (terminal) session. Reads
        three existing signals rather than tracking anything new -- see
        todo/todo_cross_surface_continuity.md.

        Each candidate is discarded if older than
        CROSS_SURFACE_STALENESS_MINUTES -- a paused track from hours ago
        isn't "picking up where you left off" anymore. Returns whichever
        surviving candidate is most recent.

        `frame.persisted_now_playing`/`frame.launcher_context.surface_state` (SA-4) replace
        this rule's own NOW_PLAYING_CONFIG_KEY/SURFACE_STATE_CONFIG_KEY reads --
        check_now_playing() reads the same now-playing config row, and the surface-state row
        isn't duplicated elsewhere but moved into the frame for consistency. The routines
        query below isn't duplicated by anything else, so it stays its own query.
        """
        now = frame.now
        staleness = timedelta(minutes=CROSS_SURFACE_STALENESS_MINUTES)
        candidates = []

        now_playing = frame.persisted_now_playing or {}
        if now_playing.get("is_playing") is False and now_playing.get("updated_at"):
            try:
                paused_at = datetime.fromisoformat(now_playing["updated_at"])
            except ValueError:
                paused_at = None
            if paused_at and now - paused_at <= staleness:
                title = now_playing.get("title") or "your last track"
                minutes_ago = int((now - paused_at).total_seconds() / 60)
                candidates.append(
                    (
                        paused_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": f"{title} paused {minutes_ago} min ago — resume?",
                            "priority": 5.5,
                            "resume_type": "music",
                            "resume_target": now_playing.get("track_id"),
                            "data": {"minutes_ago": minutes_ago},
                        },
                    )
                )

        surface_state = (frame.launcher_context and frame.launcher_context.surface_state) or {}
        if surface_state.get("terminal_session_active") and surface_state.get("updated_at"):
            try:
                reported_at = datetime.fromisoformat(surface_state["updated_at"])
            except ValueError:
                reported_at = None
            if reported_at and now - reported_at <= staleness:
                candidates.append(
                    (
                        reported_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": "Terminal session still open — resume on the Deck?",
                            "priority": 5.5,
                            "resume_type": "terminal",
                            "resume_target": None,
                        },
                    )
                )

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT name, updated_at FROM routines WHERE updated_at IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                name, updated_at = row
                edited_at = updated_at.replace(tzinfo=timezone.utc)
                if now - edited_at <= staleness:
                    candidates.append(
                        (
                            edited_at,
                            {
                                "mode": "cross_surface_continuity",
                                "content": f'"{name}" routine edited recently — reopen it?',
                                "priority": 5.5,
                                "resume_type": "routine",
                                "resume_target": name,
                            },
                        )
                    )
        except pymysql.Error as e:
            logger.error("Cross-surface continuity routine check error: " + str(e))
        finally:
            if db:
                db.close()

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    def _read_fresh_attention_telemetry(self):
        """Return the most recent attention-telemetry snapshot (see
        POST /api/context/attention-telemetry, routes/context.py) as a dict,
        or None if there isn't one yet or it's older than
        ATTENTION_TELEMETRY_STALENESS_MINUTES -- shared staleness gate for
        both check_attention_focus() and check_wind_down_signal()."""
        snapshot = self._read_config_json(ATTENTION_TELEMETRY_CONFIG_KEY)
        reported_at = snapshot.get("reported_at")
        if not reported_at:
            return None
        try:
            reported_dt = datetime.fromisoformat(reported_at)
        except ValueError:
            return None
        age = datetime.now(timezone.utc) - reported_dt
        if age > timedelta(minutes=ATTENTION_TELEMETRY_STALENESS_MINUTES):
            return None
        return snapshot

    @staticmethod
    def _media_dwell_fraction(dwell_by_category_ms):
        """Fraction of total reported dwell time spent in the "media"
        category -- shared by check_attention_focus() (wants this low) and
        check_wind_down_signal() (wants this high). 0.0 if there's no dwell
        data at all (rather than dividing by zero)."""
        if not dwell_by_category_ms:
            return 0.0
        total = sum(dwell_by_category_ms.values())
        if total <= 0:
            return 0.0
        return dwell_by_category_ms.get("media", 0) / total

    def _attention_telemetry_trend(self):
        """Household's own rolling switch_count/unlock_count median from
        attention_telemetry_history (SA-2), over the last
        ATTENTION_TREND_LOOKBACK_DAYS. Returns None below
        ATTENTION_TREND_MIN_SAMPLES (not enough history for a meaningful
        "typical" yet) or on a DB error -- callers fall back to the fixed
        thresholds in that case, same "degrade to silence" precedent as
        compute_entity_baselines()/check_rhythm_break_anomaly()."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT switch_count, unlock_count FROM attention_telemetry_history "
                "WHERE reported_at >= %s",
                (datetime.now(timezone.utc) - timedelta(days=ATTENTION_TREND_LOOKBACK_DAYS),),
            )
            rows = cursor.fetchall()
            if len(rows) < ATTENTION_TREND_MIN_SAMPLES:
                return None
            return {
                "sample_count": len(rows),
                "median_switch_count": statistics.median(row[0] for row in rows),
                "median_unlock_count": statistics.median(row[1] for row in rows),
            }
        except pymysql.Error as e:
            logger.error(f"Attention telemetry trend query error: {e}")
            return None
        finally:
            if db:
                db.close()

    def check_attention_focus(self, frame):
        """A measured, evidence-based focus signal from the launcher's own
        window-switching behavior -- additive alongside (not a replacement
        for) check_focus_needed()'s calendar heuristic; see
        todo/todo_attention_telemetry.md for why the two coexist rather than
        one replacing the other.

        Fires when the reported window-switch count is genuinely high --
        above this household's own rolling median switch_count plus a grace
        margin once enough history exists (`frame.launcher_context.
        attention_trend`), falling back to the fixed ATTENTION_FOCUS_MIN_SWITCHES threshold
        below that sample floor -- and that switching isn't concentrated in
        media (which would be the wind-down pattern instead, see
        check_wind_down_signal()).

        `frame.launcher_context.attention_snapshot`/`.attention_trend` (SA-4) replace this
        rule's own _read_fresh_attention_telemetry()/_attention_telemetry_trend() calls --
        check_wind_down_signal() reads the exact same two.
        """
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot:
            return None
        switch_count = snapshot.get("switch_count", 0)
        trend = launcher and launcher.attention_trend
        threshold = ATTENTION_FOCUS_MIN_SWITCHES
        if trend:
            threshold = max(
                threshold, trend["median_switch_count"] + ATTENTION_FOCUS_TREND_GRACE_SWITCHES
            )
        if switch_count < threshold:
            return None
        media_fraction = self._media_dwell_fraction(snapshot.get("dwell_by_category_ms") or {})
        if media_fraction >= ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION:
            return None
        return {
            "mode": "attention_focus",
            "content": f"Deep in it — {switch_count} window switches recently",
            "priority": 3.6,
            "switch_count": switch_count,
            "data": {
                "because": [
                    f"{switch_count} switches >= threshold {threshold}",
                    f"media dwell {media_fraction:.0%} < "
                    f"{ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION:.0%}",
                ]
            },
        }

    def check_wind_down_signal(self, frame):
        """The milestone's own "inverse case": late-hour high unlock rate +
        media-heavy dwell suggests winding down. Suggestion card only --
        does not auto-actuate lights/Spotify itself, matching every other
        card in this file (informational, never autonomous device control).

        Fires above this household's own rolling median unlock_count plus a
        grace margin once enough history exists
        (`frame.launcher_context.attention_trend`), falling back to the fixed
        WIND_DOWN_MIN_UNLOCKS threshold below that sample floor -- same
        trend-vs-fallback shape as check_attention_focus().

        `frame.day_mood`/`frame.launcher_context.attention_snapshot`/`.attention_trend`
        (SA-4) replace this rule's own get_env_local_time()/get_day_mood()/
        _read_fresh_attention_telemetry()/_attention_telemetry_trend() calls.
        """
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot:
            return None
        if frame.day_mood is None or frame.day_mood["time_of_day"] != "night":
            return None
        unlock_count = snapshot.get("unlock_count", 0)
        trend = launcher and launcher.attention_trend
        threshold = WIND_DOWN_MIN_UNLOCKS
        if trend:
            threshold = max(threshold, trend["median_unlock_count"] + WIND_DOWN_TREND_GRACE_UNLOCKS)
        if unlock_count < threshold:
            return None
        media_fraction = self._media_dwell_fraction(snapshot.get("dwell_by_category_ms") or {})
        if media_fraction < WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:
            return None
        return {
            "mode": "wind_down_signal",
            "content": f"Lots of screen time tonight ({unlock_count} unlocks) — wind down?",
            "priority": 5.8,
            "unlock_count": unlock_count,
            "data": {
                "because": [
                    f"{unlock_count} unlocks >= threshold {threshold}",
                    f"media dwell {media_fraction:.0%} >= {WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:.0%}",
                    "night",
                ]
            },
        }

    def check_party_advisory(self, frame):
        """Catch a real, high-energy gathering happening despite the capped
        weeknight recommendation -- e.g. someone manually queues something
        rowdy on a Tuesday -- and nudge toward winding down.

        `common.spotify_utils.recommend()` only ever *suggests* capped
        energy on non-party nights (see its `is_party_night` param); nothing
        stops residents/guests from playing something high-energy anyway.
        This checks what's actually playing via Spotify's own 0.0-1.0
        'energy' audio feature for the current track, independent of
        ALFR3D's own estimate. Only evaluated outside the household's
        declared Friday/Saturday party-night window and once it's genuinely
        late (time_of_day == "night"), not just any weeknight evening.

        The returned card refreshes every cycle like any other display, but
        the spoken nudge over the `speak` topic is cooldown-gated
        (PARTY_ADVISORY_COOLDOWN_MINUTES) so it doesn't repeat the same
        "school night" line every polling cycle.

        `frame.local_dt`/`frame.day_mood`/`frame.playback` (SA-4) replace this rule's own
        get_env_local_time()/get_day_mood()/get_playback_state() calls --
        check_gatherings()/check_wind_down_signal()/check_mood() share the first two,
        check_now_playing() shares the third. get_track_energy() below stays its own call --
        a different Spotify endpoint (audio features, not playback state) that depends on
        the track id this same fetch already resolved, so there's nothing to share it with.
        """
        global PARTY_ADVISORY_LAST_NUDGE_TIME
        try:
            if frame.local_dt is None or frame.day_mood is None:
                return None
            local_dt = frame.local_dt
            if spotify_utils.is_party_night(local_dt):
                return None

            day_mood = frame.day_mood
            if day_mood["time_of_day"] != "night":
                return None

            from common import spotify_utils as spotify_api

            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            if not state.get("is_playing") or not track_id:
                return None

            energy = spotify_api.get_track_energy(track_id)
            if energy is None or energy < PARTY_ADVISORY_ENERGY_THRESHOLD:
                return None

            track_name = item.get("name") or "the music"
            content = (
                f'"{track_name}" is still high-energy for a {day_mood["day_of_week"]} '
                "night -- work tomorrow, might be worth winding down."
            )

            if time.time() - PARTY_ADVISORY_LAST_NUDGE_TIME > PARTY_ADVISORY_COOLDOWN_MINUTES * 60:
                p = get_producer()
                if p:
                    p.send(
                        "speak",
                        (
                            f'Hey, it\'s a {day_mood["day_of_week"]} night and the music is '
                            "still pretty high energy. Just a heads up, it's a work night."
                        ).encode("utf-8"),
                    )
                PARTY_ADVISORY_LAST_NUDGE_TIME = time.time()

            return {
                "mode": "party_advisory",
                "content": content,
                "priority": 3.2,
                "data": {
                    "track_name": track_name,
                    "energy": energy,
                    "day_of_week": day_mood["day_of_week"],
                    "because": [
                        f"track energy {energy:.2f} >= {PARTY_ADVISORY_ENERGY_THRESHOLD}",
                        f"{day_mood['day_of_week']} night",
                    ],
                },
            }
        except Exception as e:
            logger.error("Party advisory check error: " + str(e))
            return None

    def check_weather(self, frame):
        """Default: concise weather summary.

        `frame.environment` (SA-4) replaces this rule's own environment-table read --
        check_weather_advisory()/check_gatherings() each ran their own separate query
        against the exact same row.
        """
        environment = frame.environment
        if not environment:
            return None
        content = (
            f"{environment['city']}: {environment['subjective_feel']}, "
            f"{environment['description']}, {environment['low']}°C to {environment['high']}°C"
        )
        return {
            "mode": "weather",
            "content": content,
            "priority": 5,
            "data": {
                "city": environment["city"],
                "subjective_feel": environment["subjective_feel"],
                "description": environment["description"],
                "low": environment["low"],
                "high": environment["high"],
            },
        }

    def check_weather_advisory(self, frame):
        """Forward-looking rain advisory for the home location.

        Reads the forecast snapshot service_environment persists to the
        environment table (via its "check forecast" Kafka message and
        weather_util.get_forecast()) -- the same direct-DB-read pattern
        check_weather() uses for current conditions, rather than a
        synchronous cross-service call. Home location only; per-destination
        forecasting would need geocoding calendar_events.address and is out
        of scope here.

        `frame.environment` (SA-4) replaces this rule's own environment-table read --
        see check_weather()'s docstring for the duplicate this and check_gatherings() shared.
        """
        environment = frame.environment
        if not environment:
            return None
        rain_probability = environment.get("forecast_rain_probability")
        if rain_probability is not None and rain_probability > RAIN_ADVISORY_THRESHOLD:
            content = f"Rain likely in the next {FORECAST_HOURS_AHEAD} hours — bring an umbrella"
            return {
                "mode": "weather_advisory",
                "content": content,
                "priority": 4.5,
                "data": {
                    "forecast_rain_probability": rain_probability,
                    "hours_ahead": FORECAST_HOURS_AHEAD,
                    "because": [
                        f"{rain_probability}% rain probability > {RAIN_ADVISORY_THRESHOLD}%"
                    ],
                },
            }
        return None

    def check_time(self, frame):
        """Get current time card.

        `frame.now` (SA-4) replaces this rule's own datetime.now(timezone.utc) call -- every
        card published this cycle now shares the exact same timestamp.
        """
        content = frame.now.isoformat()
        return {"mode": "time", "content": content, "priority": 1}

    def check_mood(self, frame):
        """Baseline day-mood card: weekday/time-of-day context with a qualitative energy read.

        `frame.day_mood` (SA-4) replaces this rule's own get_env_local_time()/get_day_mood()
        calls -- check_gatherings()/check_party_advisory()/check_wind_down_signal() all
        needed the exact same pair.
        """
        if frame.day_mood is None:
            return None
        day_mood = frame.day_mood
        energy = day_mood["base_energy"]
        if energy < 0.35:
            energy_label = "low energy"
        elif energy < 0.65:
            energy_label = "moderate energy"
        else:
            energy_label = "high energy"
        content = f"{day_mood['day_of_week']} {day_mood['time_of_day']} — {energy_label}"
        return {
            "mode": "mood",
            "content": content,
            "priority": 6,
            "data": {
                "day_of_week": day_mood["day_of_week"],
                "time_of_day": day_mood["time_of_day"],
                "energy": energy,
                "energy_label": energy_label,
            },
        }

    def scan_devices(self):
        logger.info("Time for localnet scan")
        p = get_producer()
        if p:
            p.send("device", orjson.dumps({"action": "scan_net"}))

    def check_routines(self):
        logger.info("Routine check")
        util_routines.check_routines()

    def check_mute_status(self):
        logger.info("Checking if mute")
        return self.check_mute()

    def perform_waking_hours_tasks(self):
        try:
            logger.info("Is it time for a smartass quip?")
            self.be_smart()
        except KafkaError as e:
            logger.error("Failed to complete the quip block")
            logger.error("Traceback: " + str(e))
        try:
            logger.info("Time to check Gmail")
            self.check_emails()
        except KafkaError as e:
            logger.error("Failed to check Gmail")
            logger.error("Traceback: " + str(e))

    def publish_sa(self, data):
        """Publish array of SA cards to Kafka topic."""
        p = get_producer()
        if p:
            p.send("situational-awareness", orjson.dumps(data))
            logger.info("Published situational awareness: " + str(data))


def reset_routines():
    """
    Description:
            refresh some things at midnight
    """
    logger.info("Time to reset routines")
    util_routines.reset_routines()


def check_weather_routine():
    """
    Description:
            Send a weather check message to the environment topic every 4 hours.
    """
    logger.info("Scheduled weather check")
    p = get_producer()
    if p:
        p.send("environment", b"check weather")


def check_forecast_routine():
    """
    Description:
            Send a forecast check message to the environment topic every hour,
            so check_weather_advisory() has a reasonably fresh forecast snapshot
            to read from the environment table.
    """
    logger.info("Scheduled forecast check")
    p = get_producer()
    if p:
        p.send("environment", b"check forecast")


def sync_iot_devices():
    """
    Description:
            Send IoT sync messages to the device topic every 15 minutes.
    """
    logger.info("Scheduled IoT device sync")
    p = get_producer()
    if p:
        p.send("device", orjson.dumps({"action": "iot_ha_sync"}))
        p.send("device", orjson.dumps({"action": "iot_st_sync"}))
        p.send("device", orjson.dumps({"action": "iot_esphome_sync"}))


def discover_esphome_devices():
    """
    Description:
            Send an ESPHome mDNS discovery scan message to the device topic every hour.
            Separate cadence from sync_iot_devices()'s 15-minute entity sync: discovery is a
            blocking LAN scan (see esphome_utils.discover_esphome_nodes) and only needs to run
            often enough to catch newly-added nodes, not on every entity-state sync.
    """
    logger.info("Scheduled ESPHome discovery")
    p = get_producer()
    if p:
        p.send("device", orjson.dumps({"action": "iot_esphome_discover"}))


def play_tune_scheduled():
    """
    Description:
            Play a context-aware tune (scheduled, e.g. mornings).
    """
    logger.info("Scheduled tune playback")
    daemon = MyDaemon()
    daemon.play_tune()


def rebuild_music_recommendations():
    """
    Description:
            Rebuild the music recommendation pool in the background.
    """
    logger.info("Rebuilding music recommendations")
    try:
        from common import recommender_engine

        recommender_engine.build_recommendation_pool()
    except Exception as e:
        logger.error(f"Failed to rebuild music recommendations: {str(e)}")


def _departure_hours_by_bucket(timestamps):
    """Reduce one resident's raw device_history timestamps (union of every claimed device,
    already sorted ascending) into {"weekday": [hour, ...], "weekend": [hour, ...]} -- one entry
    per day this resident's first real departure could be confirmed.

    `device_history.state` is not used here (SA-3's Phase 0 spike found it unreliable for this --
    see todo/todo_departure_anomaly.md: the `before_device_update` trigger logs each row's state
    from *before* that write, so a per-cycle "still online" ping and the offline-flip event both
    log the same value, and only a reconnect-after-absence row logs the other one). The real
    signal is in the *gaps* between consecutive writes: `device.update()` fires on every arp-scan
    sighting (~60-90s while a device is actually seen), so a gap of DEPARTURE_GAP_MINUTES+ can
    only mean the device (and everything that shares this list) went undetected for that long.

    A day only counts if this resident was confirmed home overnight (some row before 05:00) --
    without that anchor, a day's first-seen row could just be a late-morning reappearance of an
    absence that started the night before, which would misattribute a multi-day trip's single
    real departure to every day it spans.
    """
    buckets = {"weekday": [], "weekend": []}
    if len(timestamps) < 2:
        return buckets

    days_seen = set()
    for ts in timestamps:
        day = ts.date()
        if day in days_seen:
            continue
        days_seen.add(day)

        day_start_idx = bisect.bisect_left(timestamps, datetime.combine(day, dtime.min))
        if timestamps[day_start_idx].time() >= dtime(5, 0):
            continue  # no overnight confirmation -- likely spillover from a prior absence

        anchor_idx = bisect.bisect_left(timestamps, datetime.combine(day, dtime(4, 0)))
        if anchor_idx >= len(timestamps) or timestamps[anchor_idx].date() != day:
            continue

        departure = None
        for i in range(anchor_idx, len(timestamps) - 1):
            gap_minutes = (timestamps[i + 1] - timestamps[i]).total_seconds() / 60
            if gap_minutes >= DEPARTURE_GAP_MINUTES:
                departure = timestamps[i]
                break
        if departure is None:
            continue

        bucket = "weekend" if departure.weekday() >= 5 else "weekday"
        buckets[bucket].append(departure.hour)

    return buckets


def compute_entity_baselines():
    """Recompute per-entity rhythm/routine baselines into `entity_baselines`.

    Three independent baseline types share this table and this 6-hourly compute cadence, all
    derived from `device_history`, none needing a new table (SA-10 generalised the mechanism
    rather than letting each new subject bolt on its own):
    - `device` rows (original, see todo/todo_rhythm_break_anomaly.md): on/off session
      baselines used by MyDaemon.check_rhythm_break_anomaly(). `smarthome_devices` has no
      equivalent state-history table yet -- `device_command_history` logs issued commands, not
      observed state over time -- so smarthome-device baselines aren't computed;
      `entity_baselines.entity_type` keeps room for that once such a history exists (as does
      `'room'`, gated on SA-9 sensor coverage -- stopped at Phase 0 this session, no real
      ESPHome node to validate against, see todo/todo_esphome_situational_awareness.md).
    - `user` rows (SA-3, see todo/todo_departure_anomaly.md): per-resident weekday/weekend
      departure-hour baselines used by MyDaemon.check_departure_anomaly(). Guests excluded.
    - `household` rows (SA-10, see todo/todo_generalize_entity_baselines.md): weekday/weekend
      typical first/last-activity hour and device-count range for the household as a whole,
      used by MyDaemon.check_household_unusual_day(). A singleton -- one row per day_bucket,
      `entity_id` is a fixed sentinel (HOUSEHOLD_BASELINE_ENTITY_ID), not a real foreign key.
      Computed as a single SQL aggregate, not a per-entity Python loop -- see the "household
      baselines" block below for why that distinction mattered in practice, not just in theory.
    """
    logger.info("Computing entity rhythm baselines")
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT DISTINCT device_id FROM device_history WHERE timestamp >= %s",
            (datetime.now(timezone.utc) - timedelta(days=ENTITY_BASELINE_LOOKBACK_DAYS),),
        )
        device_ids = [row[0] for row in cursor.fetchall()]

        for device_id in device_ids:
            cursor.execute(
                """
                SELECT dh.timestamp, s.state
                FROM device_history dh
                JOIN states s ON dh.state = s.id
                WHERE dh.device_id = %s
                  AND dh.timestamp >= %s
                  AND s.state IN ('online', 'offline')
                ORDER BY dh.timestamp ASC
                """,
                (
                    device_id,
                    datetime.now(timezone.utc) - timedelta(days=ENTITY_BASELINE_LOOKBACK_DAYS),
                ),
            )
            rows = cursor.fetchall()

            durations_minutes = []
            start_hours = []
            session_start = None
            for row_timestamp, state in rows:
                if state == "online" and session_start is None:
                    session_start = row_timestamp
                elif state == "offline" and session_start is not None:
                    duration = (row_timestamp - session_start).total_seconds() / 60
                    if duration > 0:
                        durations_minutes.append(duration)
                        start_hours.append(session_start.hour)
                    session_start = None

            if len(durations_minutes) < ENTITY_BASELINE_MIN_SAMPLES:
                continue

            cursor.execute(
                """
                INSERT INTO entity_baselines
                    (entity_type, entity_id, median_on_minutes, typical_active_hour,
                     typical_daily_min, typical_daily_max, sample_count, min_sample_count,
                     computed_at)
                VALUES ('device', %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    median_on_minutes = VALUES(median_on_minutes),
                    typical_active_hour = VALUES(typical_active_hour),
                    typical_daily_min = VALUES(typical_daily_min),
                    typical_daily_max = VALUES(typical_daily_max),
                    sample_count = VALUES(sample_count),
                    min_sample_count = VALUES(min_sample_count),
                    computed_at = VALUES(computed_at)
                """,
                (
                    device_id,
                    statistics.median(durations_minutes),
                    statistics.mode(start_hours),
                    min(durations_minutes),
                    max(durations_minutes),
                    len(durations_minutes),
                    ENTITY_BASELINE_MIN_SAMPLES,
                    datetime.now(timezone.utc),
                ),
            )

        # SA-3: per-resident departure-hour baselines, entity_type='user'. Same table, same
        # compute cadence -- see _departure_hours_by_bucket()'s own doc comment for why this
        # doesn't reuse the online/offline state-column reconstruction above. Guests excluded via
        # the same ut.type convention services.common.db_utils's "worthy listeners" check already
        # uses (owner/technoking/resident only).
        tz_offset = timedelta(seconds=db_utils.get_env_timezone(ENV_NAME))
        departure_lookback_start = datetime.now(timezone.utc) - timedelta(
            days=DEPARTURE_BASELINE_LOOKBACK_DAYS
        )
        cursor.execute(
            """
            SELECT DISTINCT u.id, u.username
            FROM user u
            JOIN user_types ut ON u.type = ut.id
            JOIN device d ON d.user_id = u.id
            WHERE ut.type IN ('owner', 'technoking', 'resident')
            """
        )
        eligible_users = cursor.fetchall()

        for user_id, username in eligible_users:
            cursor.execute("SELECT id FROM device WHERE user_id = %s", (user_id,))
            device_ids = [row[0] for row in cursor.fetchall()]
            if not device_ids:
                continue

            placeholders = ",".join(["%s"] * len(device_ids))
            cursor.execute(
                f"""
                SELECT timestamp FROM device_history
                WHERE device_id IN ({placeholders}) AND timestamp >= %s
                ORDER BY timestamp ASC
                """,
                (*device_ids, departure_lookback_start),
            )
            local_timestamps = sorted(row[0] + tz_offset for row in cursor.fetchall())
            buckets = _departure_hours_by_bucket(local_timestamps)

            for day_bucket, hours in buckets.items():
                if len(hours) < DEPARTURE_BASELINE_MIN_SAMPLES:
                    continue
                cursor.execute(
                    """
                    INSERT INTO entity_baselines
                        (entity_type, entity_id, day_bucket, typical_active_hour,
                         typical_daily_min, typical_daily_max, sample_count, min_sample_count,
                         computed_at)
                    VALUES ('user', %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        typical_active_hour = VALUES(typical_active_hour),
                        typical_daily_min = VALUES(typical_daily_min),
                        typical_daily_max = VALUES(typical_daily_max),
                        sample_count = VALUES(sample_count),
                        min_sample_count = VALUES(min_sample_count),
                        computed_at = VALUES(computed_at)
                    """,
                    (
                        user_id,
                        day_bucket,
                        statistics.mode(hours),
                        min(hours),
                        max(hours),
                        len(hours),
                        DEPARTURE_BASELINE_MIN_SAMPLES,
                        datetime.now(timezone.utc),
                    ),
                )
            logger.info(f"Departure baseline for {username}: {buckets}")

        # SA-10: household-level baselines, entity_type='household'. Unlike the device/user
        # loops above, this is a single SQL aggregate (GROUP BY local calendar day), not a
        # per-entity Python session-reconstruction loop -- deliberately, since Phase 0 measured
        # the existing device loop alone taking ~175s on the production NUC (see
        # todo/todo_generalize_entity_baselines.md); adding another loop of that shape for a new
        # subject type would multiply that cost, an aggregate query doesn't.
        household_lookback_start = datetime.now(timezone.utc) - timedelta(
            days=HOUSEHOLD_BASELINE_LOOKBACK_DAYS
        )
        # A derived table computing local_date once, grouped by that bare column, rather than
        # GROUP BY on an inline expression with the raw `timestamp` column also referenced in
        # the SELECT list -- MySQL's ONLY_FULL_GROUP_BY mode (the production default) rejects
        # the latter even though DAYOFWEEK(local_date) is functionally dependent on it; caught
        # live against the real database, not something the mocked unit tests could catch.
        cursor.execute(
            """
            SELECT
                DAYOFWEEK(local_date) AS local_dow,
                HOUR(first_ts) AS first_hour,
                HOUR(last_ts) AS last_hour,
                device_count
            FROM (
                SELECT
                    DATE(timestamp + INTERVAL %s SECOND) AS local_date,
                    MIN(timestamp + INTERVAL %s SECOND) AS first_ts,
                    MAX(timestamp + INTERVAL %s SECOND) AS last_ts,
                    COUNT(DISTINCT device_id) AS device_count
                FROM device_history
                WHERE timestamp >= %s
                GROUP BY local_date
            ) AS daily
            """,
            (
                tz_offset.total_seconds(),
                tz_offset.total_seconds(),
                tz_offset.total_seconds(),
                household_lookback_start,
            ),
        )
        household_buckets = {"weekday": [], "weekend": []}
        for local_dow, first_hour, last_hour, device_count in cursor.fetchall():
            # MySQL DAYOFWEEK: 1=Sunday ... 7=Saturday.
            bucket = "weekend" if local_dow in (1, 7) else "weekday"
            household_buckets[bucket].append((first_hour, last_hour, device_count))

        for day_bucket, samples in household_buckets.items():
            if len(samples) < HOUSEHOLD_BASELINE_MIN_SAMPLES:
                continue
            first_hours = [s[0] for s in samples]
            last_hours = [s[1] for s in samples]
            device_counts = [s[2] for s in samples]
            cursor.execute(
                """
                INSERT INTO entity_baselines
                    (entity_type, entity_id, day_bucket, typical_active_hour,
                     typical_last_activity_hour, typical_daily_min, typical_daily_max,
                     sample_count, min_sample_count, computed_at)
                VALUES ('household', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    typical_active_hour = VALUES(typical_active_hour),
                    typical_last_activity_hour = VALUES(typical_last_activity_hour),
                    typical_daily_min = VALUES(typical_daily_min),
                    typical_daily_max = VALUES(typical_daily_max),
                    sample_count = VALUES(sample_count),
                    min_sample_count = VALUES(min_sample_count),
                    computed_at = VALUES(computed_at)
                """,
                (
                    HOUSEHOLD_BASELINE_ENTITY_ID,
                    day_bucket,
                    statistics.mode(first_hours),
                    statistics.mode(last_hours),
                    min(device_counts),
                    max(device_counts),
                    len(samples),
                    HOUSEHOLD_BASELINE_MIN_SAMPLES,
                    datetime.now(timezone.utc),
                ),
            )
        sample_counts = {bucket: len(samples) for bucket, samples in household_buckets.items()}
        logger.info(f"Household baseline sample counts: {sample_counts}")

        db.commit()
    except pymysql.Error as e:
        logger.error(f"Entity baseline computation error: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def prune_household_events():
    """Delete household_events rows older than HOUSEHOLD_EVENTS_RETENTION_DAYS.

    household_events is written to on every event-stream message (see
    service_api's consume_events(), SA-11 Phase 1) -- the highest-volume
    table in the schema by a wide margin. Run on the same cadence as
    compute_entity_baselines() rather than a separate schedule.
    """
    logger.info("Pruning old household_events rows")
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cutoff = datetime.now(timezone.utc) - timedelta(days=HOUSEHOLD_EVENTS_RETENTION_DAYS)
        cursor.execute("DELETE FROM household_events WHERE occurred_at < %s", (cutoff,))
        deleted = cursor.rowcount
        db.commit()
        logger.info(f"Pruned {deleted} household_events rows older than {cutoff.isoformat()}")
    except pymysql.Error as e:
        logger.error(f"Household events prune error: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def prune_attention_telemetry_history():
    """Delete attention_telemetry_history rows older than
    ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS (SA-2). Run on the same cadence
    as compute_entity_baselines()/prune_household_events() rather than a
    separate schedule.
    """
    logger.info("Pruning old attention_telemetry_history rows")
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS
        )
        cursor.execute("DELETE FROM attention_telemetry_history WHERE reported_at < %s", (cutoff,))
        deleted = cursor.rowcount
        db.commit()
        logger.info(
            f"Pruned {deleted} attention_telemetry_history rows older than {cutoff.isoformat()}"
        )
    except pymysql.Error as e:
        logger.error(f"Attention telemetry history prune error: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def init_daemon():
    """
    Description:
            initialize alfr3d services
    """
    logger.info("Initializing systems check")
    p = get_producer()
    if p:
        p.send("speak", b"Initializing systems checks")

    faults = 0

    logger.info("syncing calendar events")
    p.send("speak", b"Synchronising calendar events")
    calendar_utils.sync_calendar()

    logger.info("syncing gmail emails")
    p.send("speak", b"Synchronising gmail emails")
    gmail_utils.sync_gmail()

    # initial geo check
    logger.info("Running a geoscan")
    p.send("speak", b"Running a geoscan")
    p = get_producer()
    if p:
        p.send("environment", b"check location")
        p.send("environment", b"check weather")
        p.send("environment", b"check forecast")

    # set up some routine schedules
    try:
        logger.info("Setting up scheduled routines")
        p = get_producer()
        if p:
            p.send("speak", b"Setting up scheduled routines")
            event = {
                "id": f"schedule_setup_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "info",
                "message": "Set up scheduled routines",
                "time": datetime.now(timezone.utc).isoformat(),
            }
            p.send("event-stream", orjson.dumps(event))
        # utilities.createRoutines()
        # Routine flags are reset once per day by run() when the environment's
        # local date rolls over (see MyDaemon.run), not at container UTC midnight.

        # "8.30" in the following function is just a placeholder
        # until i deploy a more configurable alarm clock
        schedule.every(4).hours.do(check_weather_routine)
        schedule.every(1).hours.do(check_forecast_routine)
        schedule.every(15).minutes.do(sync_iot_devices)
        schedule.every(60).minutes.do(discover_esphome_devices)
        schedule.every().day.at("08:00").do(play_tune_scheduled)
        schedule.every(6).hours.do(rebuild_music_recommendations)
        schedule.every(6).hours.do(compute_entity_baselines)
        schedule.every(6).hours.do(prune_household_events)
        schedule.every(6).hours.do(prune_attention_telemetry_history)
        # schedule.every().day.at(str(bed_time.hour)+":"+str(bed_time.minute)).do(bedtime_routine)
    except Exception as e:
        logger.error("Failed to set schedules")
        logger.error("Traceback: " + str(e))
        faults += 1  # bump up fault counter

    p = get_producer()
    if p:
        p.send("speak", b"Systems check is complete")
    if faults != 0:
        logger.warning("Some startup faults were detected")
        p = get_producer()
        if p:
            p.send("speak", b"Some faults were detected but system started successfully")
            event = {
                "id": f"setup_complete_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "warning",
                "message": f"System check finished with {faults} faults",
                "time": datetime.now(timezone.utc).isoformat(),
            }
            p.send("event-stream", orjson.dumps(event))

        # producer.send("speak", b"Total number of faults is "+str(faults))

    else:
        logger.info("All systems are up and operational")
        p = get_producer()
        if p:
            p.send("speak", b"All systems are up and operational")
            event = {
                "id": f"setup_complete_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "success",
                "message": "System check finished",
                "time": datetime.now(timezone.utc).isoformat(),
            }
            p.send("event-stream", orjson.dumps(event))

    return


if __name__ == "__main__":
    daemon = MyDaemon()
    if len(sys.argv) == 2:
        if "start" == sys.argv[1]:
            logger.info("Alfr3d Daemon initializing")
            init_daemon()
            threading.Thread(target=consume_integrations, daemon=True).start()
            now_playing_monitor.start_now_playing_monitor()
            logger.info("Alfr3d Daemon starting...")
            daemon.run()
        elif "test" == sys.argv[1]:
            logger.info("Running in test mode")
            daemon.check_situational_awareness()  # Simulate
            sys.exit(0)
        else:
            print("Unknown command")
            sys.exit(2)
    else:
        print("usage: %s start|test" % sys.argv[0])
        sys.exit(2)
