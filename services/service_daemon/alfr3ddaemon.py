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
from datetime import datetime, timezone
import orjson
import threading

# Third party imports
import pymysql
import schedule  # 3rd party lib used for alarm clock managment.
from utils import util_routines
from utils import now_playing_monitor
from kafka.errors import KafkaError
from kafka import KafkaConsumer  # user to write messages to Kafka

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import calendar_utils, gmail_utils, spotify_utils  # noqa: E402
from common import get_producer  # noqa: E402
from common import db_utils  # noqa: E402
from common import day_context  # noqa: E402
from common import timeofday  # noqa: E402
from common import heartbeat  # noqa: E402

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# Heartbeat file MyDaemon.run() touches at the top of every cycle. The window is wider
# than the consumer services' 90s because one cycle is a 60s sleep plus however long the
# routine/SA work takes -- 300s catches a genuinely wedged daemon without flapping on an
# ordinary slow pass. See common/heartbeat.py.
HEARTBEAT_PATH = "/tmp/daemon_heartbeat"
HEARTBEAT_STALE_SECONDS = 300


# set up daemon things
# directories created in Dockerfile

# get main DB credentials
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

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
    """Consume integration messages from Kafka integrations topic.

    Retries with backoff on any Kafka error instead of exiting. Previously a single
    failed connection (e.g. the broker still recovering from an unclean shutdown)
    killed this thread permanently, silently stopping calendar/gmail sync until
    someone noticed and restarted the daemon by hand (confirmed 2026-09-25).
    """
    retry_count = 0
    while True:
        try:
            logger.info(f"Integration consumer bootstrap servers: {KAFKA_URL}")
            consumer = KafkaConsumer(
                "integrations", bootstrap_servers=KAFKA_URL, auto_offset_reset="latest"
            )
            logger.info("Connected to Kafka integrations topic")
            retry_count = 0
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
            retry_count += 1
            wait_time = min(5 * (2 ** (retry_count - 1)), 60)
            logger.error(
                f"Error connecting to Kafka for integrations: {str(e)}, retrying in {wait_time}s"
            )
            time.sleep(wait_time)


class MyDaemon:
    def run(self):
        last_reset_date = None
        while True:
            heartbeat.touch(HEARTBEAT_PATH)
            schedule.run_pending()  # Execute any pending scheduled tasks
            local_today = db_utils.get_env_local_time(ENV_NAME).date()
            if last_reset_date is not None and local_today != last_reset_date:
                reset_routines()
            last_reset_date = local_today
            self.scan_devices()
            self.check_routines()
            if not self.check_mute_status():
                self.perform_waking_hours_tasks()
            # Situational awareness no longer runs here: it moved to service_sa (sa-awareness)
            # in LF-1a, so this loop stays fast. See todo/sa/todo_lf1a_sa_service_split.md.
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
                # Quips are already written in character; running them through the
                # "rephrase this announcement" LLM prompt made it complain about a
                # missing announcement, so speak them verbatim.
                p.send("speak", orjson.dumps({"text": quip, "skip_personality": True}))

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
            gmail_utils.check_unread_emails()
        except KafkaError as e:
            logger.error("Failed to check Gmail")
            logger.error("Traceback: " + str(e))


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


def record_weather_routine():
    """
    Description:
            Send a record-weather message to the environment topic every hour. Unlike the
            4-hourly check_weather_routine() it stores the reading silently (no announcement), so
            the SA layer gets weather history at an hourly resolution.
    """
    logger.info("Scheduled weather sample")
    p = get_producer()
    if p:
        p.send("environment", b"record weather")


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


def sync_calendar_routine():
    """
    Description:
            Trigger a Google Calendar sync every 15 minutes by publishing to the
            `integrations` topic -- the same message the API's
            /integrations/calendar/sync endpoint sends, picked up by
            consume_integrations(). Without this, calendar_events only refreshes at
            daemon startup or on a manual Sync from the Integrations page, so a
            newly-created event (e.g. one with an address that check_travel() needs)
            could sit unsynced for hours. Published, not called inline, to keep the
            schedule loop non-blocking like every other routine here.
    """
    logger.info("Scheduled calendar sync")
    p = get_producer()
    if p:
        p.send("integrations", orjson.dumps({"type": "calendar", "action": "sync"}))


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
        schedule.every(1).hours.do(record_weather_routine)
        schedule.every(1).hours.do(check_forecast_routine)
        schedule.every(15).minutes.do(sync_calendar_routine)
        schedule.every(15).minutes.do(sync_iot_devices)
        schedule.every(60).minutes.do(discover_esphome_devices)
        schedule.every().day.at("08:00").do(play_tune_scheduled)
        schedule.every(6).hours.do(rebuild_music_recommendations)
        # compute_entity_baselines() moved to service_sa's sa-learner (LF-1a), same 6h cadence.
        # household_events/attention_telemetry_history/card_interactions retention and the daily
        # SA storage-metrics snapshot moved to DB-native scheduled EVENTs (migration 039,
        # 2026-09-13) -- see that migration's own comment. Nothing schedules them from here any
        # more; they run inside MySQL's own event scheduler regardless of whether this service
        # is up.
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
            heartbeat.start_watchdog(HEARTBEAT_PATH, HEARTBEAT_STALE_SECONDS, log=logger)
            threading.Thread(target=consume_integrations, daemon=True).start()
            now_playing_monitor.start_now_playing_monitor()
            logger.info("Alfr3d Daemon starting...")
            daemon.run()
        else:
            print("Unknown command")
            sys.exit(2)
    else:
        print("usage: %s start" % sys.argv[0])
        sys.exit(2)
