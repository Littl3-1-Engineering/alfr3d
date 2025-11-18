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

# Imports
import logging
import time
import os  # used to allow execution of system level commands
import sys
import schedule  # 3rd party lib used for alarm clock managment.
from random import randint  # used for random number generator
from kafka import KafkaProducer  # user to write messages to Kafka
from datetime import datetime
import json
import pymysql

from kafka.errors import KafkaError

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# import my own utilities
sys.path.append(
    os.path.join(os.path.join(os.getcwd(), os.path.dirname(__file__)), "../")
)
from utils import util_routines
from utils import gmail_utils, maps_utils, calendar_utils, spotify_utils


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
OPENWEATHER_API_KEY = os.environ.get(
    "OPENWEATHER_API_KEY"
)  # For destination weather if needed
GAS_PRICE = float(os.environ.get("GAS_PRICE", "3.5"))  # Default gas price
MPG = float(os.environ.get("MPG", "25"))  # Default MPG

producer = None

# time of sunset/sunrise - defaults
# SUNSET_TIME = datetime.datetime.now().replace(hour=19, minute=0)
# SUNRISE_TIME = datetime.datetime.now().replace(hour=6, minute=30)
# BED_TIME = datetime.datetime.now().replace(hour=23, minute=00)

# various counters to be used for pacing spreadout functions
QUIP_START_TIME = time.time()
QUIP_WAIT_TIME = randint(5, 10)

# set up logging
logger = logging.getLogger("DaemonLog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_producer():
    global producer
    if producer is None:
        try:
            print("Connecting to Kafka at: " + KAFKA_URL)
            producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
            logger.info("Connected to Kafka")
        except KafkaError as e:
            logger.error("Failed to connect to Kafka: " + str(e))
            return None
    return producer


class MyDaemon:
    def run(self):
        while True:
            self.scan_devices()
            self.check_routines()
            if not self.check_mute_status():
                self.perform_waking_hours_tasks()
            try:
                self.check_situational_awareness()
            except Exception as e:
                logger.error("Situational awareness check failed: " + str(e))
            time.sleep(60)

    def checkGmail(self) -> None:
        """
        Description:
                 Checks the unread count in gMail
        """
        logger.info("Checking email")

        p = get_producer()
        if p:
            p.send("google", b"check gmail")

    def beSmart(self) -> None:
        """
        Description:
                 speak a quip
        """
        global QUIP_START_TIME
        global QUIP_WAIT_TIME

        if time.time() - QUIP_START_TIME > QUIP_WAIT_TIME * 60:
            logger.info("It is time to be a smartass")

            p = get_producer()
            if p:
                p.send("speak", b"alfr3d-speak.random")

            QUIP_START_TIME = time.time()
            QUIP_WAIT_TIME = randint(10, 50)
            print("Time until next quip: ", QUIP_WAIT_TIME)  # DEBUG

            logger.info("QUIP_START_TIME and QUIP_WAIT_TIME have been reset")
            logger.info(
                "Next quip will be shouted in " + str(QUIP_WAIT_TIME) + " minutes."
            )

    def playTune(self):
        """
        Description:
                pick a random song from current weather category and play it
        """
        logger.info("playing a tune")

    def nightlight(self):
        """
        Description:
                is anyone at home?
                is it after dark?
                turn the lights on or off as needed.
        """
        logger.info("nightlight auto-check")

    def checkMute(self):
        """
        Description:
                checks what time it is and decides if Alfr3d should be quiet
                - between wake-up time and bedtime
                - only when Athos is at home
                - only when 'owner' is at home
        """
        logger.info("Checking if Alfr3d should be muted")
        result = util_routines.checkMute()

        return result

    def check_situational_awareness(self):
        """Poll data and publish array of situational awareness cards."""
        results = self.decide_displays()
        if results:
            self.publish_sa(results)

    def decide_displays(self):
        """Collect up to 4 SA items: emails, events, gatherings; default to time + weather."""
        displays = []
        logger.info("Collecting displays: checking emails")
        emails = self.check_emails()
        if emails:
            displays.append(emails)
        logger.info("Collecting displays: checking events")
        events = self.check_events()
        if events:
            displays.append(events)
        logger.info("Collecting displays: checking gatherings")
        gatherings = self.check_gatherings()
        if gatherings:
            displays.append(gatherings)
        if not displays:
            logger.info("No priority displays, defaulting to time and weather")
            time_card = self.check_time()
            weather_card = self.check_weather()
            if time_card:
                displays.append(time_card)
            if weather_card:
                displays.append(weather_card)
        # Limit to 4
        return displays[:4]

    def check_emails(self):
        """Check for unread emails using Gmail utils."""
        return gmail_utils.check_unread_emails()

    def check_events(self):
        """Check for upcoming events with addresses."""
        events = calendar_utils.get_upcoming_events()
        if events:
            event = events[0]  # Take first
            title = event["title"]
            start_time = event["start_time"]
            address = event["address"]
            # Get current location from DB
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
                db.close()
                if loc_row:
                    lat, lng = loc_row
                    travel_info = maps_utils.get_travel_info(
                        lat, lng, address, start_time
                    )
                    if travel_info:
                        departure = travel_info["departure"]
                        fuel_cost = travel_info["fuel_cost"]
                        # Placeholder for dress and umbrella
                        temp = 20  # TODO: Fetch destination weather
                        rain_prob = 0
                        dress = (
                            "light jacket"
                            if 10 <= temp <= 20
                            else "shorts" if temp > 25 else "normal"
                        )
                        umbrella = "Bring umbrella" if rain_prob > 30 else ""
                        content = (f"Leave at {departure.strftime('%I:%M %p')} for {title}. "
                                   f"Wear {dress}. {umbrella}. Fuel: ~${fuel_cost:.2f}")
                        return {"mode": "event", "content": content, "priority": 2}
            except Exception as e:
                logger.error("Event location error: " + str(e))
        return None

    def check_gatherings(self):
        """Check for gatherings (>3 guests/residents online)."""
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                # "SELECT COUNT(*) FROM user WHERE state = (SELECT id FROM states WHERE state = 'online') AND type IN (SELECT id FROM user_types WHERE type IN ('guest', 'resident'))"
                "SELECT COUNT(*) FROM user WHERE state = (SELECT id FROM states WHERE state = 'online') AND type IN (SELECT id FROM user_types WHERE type IN ('guest'))"
            )
            result = cursor.fetchone()
            if result:
                count = result[0]
            else:
                count = 0
            if count > 0:
                hour = datetime.now().hour
                if 6 <= hour < 18:
                    time_of_day = "day"
                elif 18 <= hour < 22:
                    time_of_day = "evening"
                else:
                    time_of_day = "night"
                cursor.execute(
                    "SELECT description FROM environment WHERE name = %s", (ENV_NAME,)
                )
                desc_row = cursor.fetchone()
                mood = (
                    (desc_row[0] if desc_row else "unknown") + " kind of " + time_of_day
                )
                playlist = spotify_utils.get_playlist_suggestion(time_of_day, mood)
                content = f"Play {playlist}"
                return {"mode": "music", "content": content, "priority": 3}
            db.close()
        except pymysql.Error as e:
            logger.error("Gathering check error: " + str(e))
        return None

    def check_weather(self):
        """Default: concise weather summary."""
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT city, description, low, high FROM environment WHERE name = %s",
                (ENV_NAME,),
            )
            row = cursor.fetchone()
            db.close()
            if row:
                city, desc, low, high = row
                content = f"{city}: {desc}, {low}°C to {high}°C"
                return {"mode": "weather", "content": content, "priority": 4}
        except pymysql.Error as e:
            logger.error("Weather check error: " + str(e))
        return None

    def check_time(self):
        """Get current time card."""
        now = datetime.now()
        content = now.strftime("%I:%M %p")
        return {"mode": "time", "content": content, "priority": 1}

    def scan_devices(self):
        logger.info("Time for localnet scan")
        p = get_producer()
        if p:
            p.send("device", b"scan net")

    def check_routines(self):
        logger.info("Routine check")
        util_routines.checkRoutines()

    def check_mute_status(self):
        logger.info("Checking if mute")
        return self.checkMute()

    def perform_waking_hours_tasks(self):
        try:
            logger.info("Is it time for a smartass quip?")
            self.beSmart()
        except KafkaError as e:
            logger.error("Failed to complete the quip block")
            logger.error("Traceback: " + str(e))
        try:
            logger.info("Time to check Gmail")
            self.checkGmail()
        except KafkaError as e:
            logger.error("Failed to check Gmail")
            logger.error("Traceback: " + str(e))

    def publish_sa(self, data):
        """Publish array of SA cards to Kafka topic."""
        p = get_producer()
        if p:
            p.send("situational-awareness", json.dumps(data).encode("utf-8"))
            logger.info("Published situational awareness: " + str(data))


def sunriseRoutine():
    """
    Description:
            sunset routine - perform this routine 30 minutes before sunrise
            giving the users time to go see sunrise
    """
    logger.info("Pre-sunrise routine")


def morningRoutine():
    """
    Description:
            perform morning routine - ring alarm, speak weather, check email, etc..
    """
    logger.info("Time for morning routine")


def sunsetRoutine():
    """
    Description:
            routine to perform at sunset - turn on ambient lights
    """
    logger.info("Time for sunset routine")


def bedtimeRoutine():
    """
    Description:
            routine to perform at bedtime - turn on ambient lights
    """
    logger.info("Bedtime")


def resetRoutines():
    """
    Description:
            refresh some things at midnight
    """
    logger.info("Time to reset routines")
    util_routines.resetRoutines()


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

    # initial geo check
    logger.info("Running a geoscan")
    p = get_producer()
    if p:
        p.send("environment", b"check location")

    # set up some routine schedules
    try:
        logger.info("Setting up scheduled routines")
        p = get_producer()
        if p:
            p.send("speak", b"Setting up scheduled routines")
        # utilities.createRoutines()
        resetRoutines()

        # "8.30" in the following function is just a placeholder
        # until i deploy a more configurable alarm clock
        schedule.every().day.at("00:05").do(resetRoutines)
        # schedule.every().day.at(str(bed_time.hour)+":"+str(bed_time.minute)).do(bedtimeRoutine)
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
            p.send(
                "speak", b"Some faults were detected but system started successfully"
            )

        # producer.send("speak", b"Total number of faults is "+str(faults))

    else:
        logger.info("All systems are up and operational")
        p = get_producer()
        if p:
            p.send("speak", b"All systems are up and operational")

    return


if __name__ == "__main__":
    daemon = MyDaemon()
    if len(sys.argv) == 2:
        if "start" == sys.argv[1]:
            logger.info("Alfr3d Daemon initializing")
            init_daemon()
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
