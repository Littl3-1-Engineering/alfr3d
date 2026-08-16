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
import time
import os  # used to allow execution of system level commands
import sys
from random import randint  # used for random number generator
from datetime import datetime, timedelta, timezone
import orjson
import threading

# Third party imports
import pymysql
import schedule  # 3rd party lib used for alarm clock managment.
from utils import util_routines
from utils import gmail_utils, maps_utils, calendar_utils, spotify_utils, mood_utils, focus_utils
from kafka.errors import KafkaError
from kafka import KafkaConsumer  # user to write messages to Kafka

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer  # noqa: E402
from common import db_utils  # noqa: E402

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
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")  # For destination weather if needed
GAS_PRICE = float(os.environ.get("GAS_PRICE", "3.5"))  # Default gas price
MPG = float(os.environ.get("MPG", "25"))  # Default MPG

# How far ahead of a call-like event's start time check_focus_needed() will fire.
FOCUS_LEAD_MINUTES = 15

# Minimum forecast rain probability (%) for check_weather_advisory() to fire.
RAIN_ADVISORY_THRESHOLD = 30

# How far ahead the forecast checked by check_weather_advisory() looks.
FORECAST_HOURS_AHEAD = 6

# time of sunset/sunrise - defaults
# SUNSET_TIME = datetime.datetime.now().replace(hour=19, minute=0)
# SUNRISE_TIME = datetime.datetime.now().replace(hour=6, minute=30)
# BED_TIME = datetime.datetime.now().replace(hour=23, minute=00)

# various counters to be used for pacing spreadout functions
QUIP_START_TIME = time.time()
QUIP_WAIT_TIME = randint(5, 10)

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

            hour = db_utils.get_env_local_time(ENV_NAME).hour
            if 6 <= hour < 12:
                time_of_day = "morning"
            elif 12 <= hour < 18:
                time_of_day = "day"
            elif 18 <= hour < 22:
                time_of_day = "evening"
            else:
                time_of_day = "night"

            reco = spotify_utils.recommend(
                total_people=total_people,
                guest_count=guest_count,
                time_of_day=time_of_day,
                weather={"description": desc, "subjective_feel": subj},
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
    DISPLAY_RULES = (
        ("time", 1, "check_time"),
        ("event", 2, "check_events"),
        # Travel guidance has its own urgency curve -- a leave-by time relative
        # to *now*, not just the event's start time -- so it's a separate card
        # from check_events() rather than folded into it. Priority 2.5 keeps
        # it right after the event it's derived from, ahead of music.
        ("travel", 2.5, "check_travel"),
        ("music", 3, "check_gatherings"),
        # A call starting soon is more actionable/time-boxed than the ambient
        # "should I play music" gathering check, but not as centrally
        # orchestrating as an event departure — priority 3.5 sits it directly
        # between music (3) and email (4) without renumbering existing rules.
        ("focus_needed", 3.5, "check_focus_needed"),
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
    )

    # Cap on cards published per cycle. Tied to the number of registered rules so
    # that every currently-registered category can coexist — previously a hardcoded
    # [:4] slice silently dropped weather (priority 5) whenever all five checks
    # fired. Grows automatically if DISPLAY_RULES grows, so adding a rule doesn't
    # silently reintroduce the same drop.
    MAX_DISPLAYS = len(DISPLAY_RULES)

    def decide_displays(self):
        """Run every registered display rule and return non-None cards, sorted by priority."""
        displays = []
        for rule_id, _priority, check_name in self.DISPLAY_RULES:
            logger.info(f"Collecting displays: checking {rule_id}")
            card = getattr(self, check_name)()
            if card:
                displays.append(card)

        if not displays:
            logger.info("No priority displays, defaulting to time and weather")

        logger.debug("Displays before sorting: " + str(displays))
        # sort by priority
        displays.sort(key=lambda x: x["priority"])

        logger.debug("Final displays selected: " + str(displays))
        return displays[: self.MAX_DISPLAYS]

    def check_emails(self):
        """Check for unread emails using Gmail utils."""
        emails = gmail_utils.check_unread_emails()
        if emails:
            email = emails[0]  # Take first
            content_lines = f"From: {email['sender']}, Subject: {email['subject']}"
            content = f"Unread Email - {content_lines} | Total Unread: {len(emails)}"
            return {"mode": "email", "content": content, "priority": 4}

    def check_events(self):
        """Check for upcoming events, showing plain title/time info.

        Travel-specific guidance (leave-by time, fuel cost) lives in
        check_travel() instead -- see its docstring for why this stays
        separate rather than folded into this card.
        """
        events = calendar_utils.get_upcoming_events()
        if not events:
            return None
        event = events[0]  # Take first
        if event["start_time"] - datetime.now(timezone.utc) > timedelta(hours=3):
            return None  # Only care about events within next hour
        title = event["title"]
        start_time = event["start_time"]
        content = f"Upcoming event: {title} at {start_time.strftime('%I:%M %p')}"
        return {"mode": "event", "content": content, "priority": 2}

    def check_travel(self):
        """Check whether the next upcoming event needs travel guidance.

        Reuses calendar_utils.get_upcoming_events() (same source check_events()
        uses). Travel timing has its own urgency curve -- a leave-by time
        relative to *now*, not just the event's start time -- so it's its own
        card rather than folded into check_events(). check_events() never
        mentions departure time or fuel cost, so there's no double-reporting
        of the same trip between the two cards even when both fire for the
        same event.

        Returns None (no card) whenever travel info can't be computed --
        missing address, no known current location, or maps_utils.get_travel_info()
        failing -- rather than falling back to fabricated numbers. check_events()
        still shows the plain event line in that case.
        """
        events = calendar_utils.get_upcoming_events()
        if not events:
            return None
        event = events[0]
        address = event["address"]
        if not address:
            return None
        start_time = event["start_time"]
        if start_time - datetime.now(timezone.utc) > timedelta(hours=3):
            return None

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT latitude, longitude FROM environment WHERE name = %s",
                (ENV_NAME,),
            )
            loc_row = cursor.fetchone()
        except Exception as e:
            logger.error("Travel location error: " + str(e))
            return None
        finally:
            if db:
                db.close()

        if not loc_row:
            logger.warning("No location data found in environment table")
            return None

        lat, lng = loc_row
        travel_info = maps_utils.get_travel_info(lat, lng, address, start_time)
        if not travel_info:
            return None

        title = event["title"]
        departure = travel_info["departure"]
        fuel_cost = travel_info["fuel_cost"]
        content = f"Leave at {departure.strftime('%I:%M %p')} for {title}. Fuel: ~${fuel_cost:.2f}"
        return {"mode": "travel", "content": content, "priority": 2.5}

    def check_focus_needed(self):
        """Check whether the next upcoming event looks like a call starting soon.

        Reuses calendar_utils.get_upcoming_events() (same source check_events()
        uses) and applies focus_utils.looks_like_call() — a text heuristic over
        the event's address/notes, not a real conferencing signal. See
        focus_utils' module docstring for its known false positive/negative
        shape. Only fires within FOCUS_LEAD_MINUTES of the event's start.
        """
        events = calendar_utils.get_upcoming_events()
        if not events:
            return None
        event = events[0]
        if not focus_utils.looks_like_call(event["address"], event["notes"]):
            return None
        start_time = event["start_time"]
        if start_time - datetime.now(timezone.utc) > timedelta(minutes=FOCUS_LEAD_MINUTES):
            return None
        title = event["title"]
        content = (
            f"Call starting soon: {title} at {start_time.strftime('%I:%M %p')}. "
            "Find a quiet spot."
        )
        return {"mode": "focus_needed", "content": content, "priority": 3.5}

    def check_gatherings(self):
        """Check for gatherings (>3 guests/residents online)."""
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
            guest_count = row[0] if row and row[0] else 0
            total_count = row[1] if row and row[1] else 0

            if guest_count > 0:
                logger.info(
                    "Gathering detected with total people: "
                    + str(total_count)
                    + " (guests: "
                    + str(guest_count)
                    + ")"
                )
                time_of_day = mood_utils.get_day_mood(db_utils.get_env_local_time(ENV_NAME))[
                    "time_of_day"
                ]
                cursor.execute(
                    "SELECT description, subjective_feel FROM environment WHERE name = %s",
                    (ENV_NAME,),
                )
                desc_row = cursor.fetchone()
                desc, subj = desc_row if desc_row else (None, None)
                weather_info = {"description": desc, "subjective_feel": subj}

                reco = spotify_utils.recommend(
                    total_people=total_count,
                    guest_count=guest_count,
                    time_of_day=time_of_day,
                    weather=weather_info,
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
                card = {"mode": "music", "content": content, "priority": 3}
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

    def check_weather(self):
        """Default: concise weather summary."""
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT city, description, low, high, subjective_feel "
                "FROM environment WHERE name = %s",
                (ENV_NAME,),
            )
            row = cursor.fetchone()
            db.close()
            if row:
                city, desc, low, high, feel = row
                content = f"{city}: {feel}, {desc}, {low}°C to {high}°C"
                return {"mode": "weather", "content": content, "priority": 5}
        except pymysql.Error as e:
            logger.error("Weather check error: " + str(e))
        return None

    def check_weather_advisory(self):
        """Forward-looking rain advisory for the home location.

        Reads the forecast snapshot service_environment persists to the
        environment table (via its "check forecast" Kafka message and
        weather_util.get_forecast()) -- the same direct-DB-read pattern
        check_weather() uses for current conditions, rather than a
        synchronous cross-service call. Home location only; per-destination
        forecasting would need geocoding calendar_events.address and is out
        of scope here.
        """
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT forecast_rain_probability FROM environment WHERE name = %s",
                (ENV_NAME,),
            )
            row = cursor.fetchone()
            db.close()
            if row and row[0] is not None and row[0] > RAIN_ADVISORY_THRESHOLD:
                content = (
                    f"Rain likely in the next {FORECAST_HOURS_AHEAD} hours — bring an umbrella"
                )
                return {"mode": "weather_advisory", "content": content, "priority": 4.5}
        except pymysql.Error as e:
            logger.error("Weather advisory check error: " + str(e))
        return None

    def check_time(self):
        """Get current time card."""
        now = datetime.now(timezone.utc)
        content = now.isoformat()
        return {"mode": "time", "content": content, "priority": 1}

    def check_mood(self):
        """Baseline day-mood card: weekday/time-of-day context with a qualitative energy read."""
        day_mood = mood_utils.get_day_mood(db_utils.get_env_local_time(ENV_NAME))
        energy = day_mood["base_energy"]
        if energy < 0.35:
            energy_label = "low energy"
        elif energy < 0.65:
            energy_label = "moderate energy"
        else:
            energy_label = "high energy"
        content = f"{day_mood['day_of_week']} {day_mood['time_of_day']} — {energy_label}"
        return {"mode": "mood", "content": content, "priority": 6}

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
        schedule.every().day.at("08:00").do(play_tune_scheduled)
        schedule.every(6).hours.do(rebuild_music_recommendations)
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
