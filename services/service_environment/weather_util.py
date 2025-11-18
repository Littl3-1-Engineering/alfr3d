# Adapted for containerization: logging to stdout, MySQLdb to pymysql
"""Utility functions for fetching and processing weather data from OpenWeatherMap API."""
import json  # used to handle jsons returned from www
import os  # used to allow execution of system level commands
import math  # used to round numbers
import logging  # needed for useful logs
import socket
import pymysql  # Changed from MySQLdb
import sys
from kafka import KafkaProducer
from time import strftime, localtime  # needed to obtain time
from datetime import datetime, timedelta
from urllib.request import urlopen  # used to make calls to www
from random import randint

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("WeatherLog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Changed to stream handler for container logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# get main DB credentials
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mysql")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")
MYSQL_USER = os.environ.get("MYSQL_USER", "user")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "password")
KAFKA_URL = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ALFR3D_ENV_NAME = os.environ.get("ALFR3D_ENV_NAME", socket.gethostname())

producer = None


def get_producer():
    global producer
    if producer is None:
        try:
            print("Connecting to Kafka at: " + KAFKA_URL)
            producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
            logger.info("Connected to Kafka")
        except Exception:
            logger.error("Failed to connect to Kafka")
            return None
    return producer


def parse_weather(cursor, lat, lon):
    logger.info("getting API key for openWeather from DB")
    cursor.execute("SELECT * from config WHERE name = %s", ("openWeather",))
    data = cursor.fetchone()

    if data:
        logger.info("Found API key")
        apikey = data[2]
    else:
        logger.warning("Failed to get API key for openWeather")
        return None

    weatherData = None

    url = (
        "https://api.openweathermap.org/data/2.5/weather?lat="
        + str(lat)
        + "&lon="
        + str(lon)
        + "&units=metric&appid="
        + apikey
    )
    try:
        weatherData = json.loads(urlopen(url).read().decode("utf-8"))
    except Exception as e:
        logger.error("Failed to get weather data\n")
        logger.error("URL: " + url)
        logger.error("Traceback " + str(e))
        return None

    logger.info("got weather data")
    logger.debug(weatherData)  # DEBUG

    # log current conditions
    logger.info("City:                           " + str(weatherData["name"]))
    logger.info("Wind Speed:                     " + str(weatherData["wind"]["speed"]))
    logger.info("Atmospheric Pressure            " + str(weatherData["main"]["pressure"]))
    logger.info("Humidity                        " + str(weatherData["main"]["humidity"]))
    logger.info("Today's Low:                    " + str(weatherData["main"]["temp_min"]))
    logger.info("Today's High:                   " + str(weatherData["main"]["temp_max"]))
    logger.info("Description:                    "+ str(weatherData["weather"][0]["description"]))
    logger.info("Current Temperature:            " + str(weatherData["main"]["temp"]))
    logger.info("Sunrise:                        "+ datetime.fromtimestamp(weatherData["sys"]["sunrise"]).strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Sunset:                         "+ datetime.fromtimestamp(weatherData["sys"]["sunset"]).strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Parsed weather data\n")

    return weatherData

def update_db_weather(db, cursor, weatherData):
    logger.info("Updating weather data in DB")

    try:
        cursor.execute(
            "UPDATE environment SET description = %s, low = %s, high = %s, "
            "sunrise = %s, sunset = %s, pressure = %s, humidity = %s WHERE name = %s",
            (
                str(weatherData["weather"][0]["description"]),
                int(weatherData["main"]["temp_min"]),
                int(weatherData["main"]["temp_max"]),
                datetime.fromtimestamp(weatherData["sys"]["sunrise"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                datetime.fromtimestamp(weatherData["sys"]["sunset"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                int(weatherData["main"]["pressure"]),
                int(weatherData["main"]["humidity"]),
                ALFR3D_ENV_NAME,
            ),
        )
        db.commit()
        logger.info("Environment weather info updated")
        return True
    except Exception as e:
        logger.error("Failed to update Environment database with weather info")
        logger.error("Traceback " + str(e))
        db.rollback()
        return False


def update_routines(db, cursor, weatherData):
    # update times for sunrise and sunset routines
    # set sunrise/sunset routines to trigger half hour before the
    # actual event so that listeners have time to take action
    try:
        logger.info("Updating routines")
        sunrise_trig = datetime.fromtimestamp(
            weatherData["sys"]["sunrise"]
        ) - timedelta(hours=0, minutes=30)
        sunset_trig = datetime.fromtimestamp(weatherData["sys"]["sunset"]) - timedelta(
            hours=0, minutes=30
        )
        cursor.execute("SELECT * FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_data = cursor.fetchone()

        if not env_data:
            logger.error("Environment not found for " + ALFR3D_ENV_NAME)
            return False
        env_id = env_data[0]
        cursor.execute(
            "UPDATE routines SET time = CASE name WHEN 'Sunrise' THEN %s "
            "WHEN 'Sunset' THEN %s END, triggered = 0 WHERE name IN ('Sunrise', 'Sunset') "
            "AND environment_id = %s",
            (
                sunrise_trig.strftime("%H:%M:%S"),
                sunset_trig.strftime("%H:%M:%S"),
                env_id,
            ),
        )
        db.commit()
        return True
    except Exception:
        logger.error("Failed to update Routines database with daytime info")
        db.rollback()
        return False


def speak_weather(weatherData):
    # Subjective weather
    badDay = []
    badDay_data = []
    badDay.append(False)
    badDay.append(badDay_data)

    # if weather is bad...
    if weatherData["weather"][0]["main"] in [
        "Thunderstorm",
        "Drizzle",
        "Rain",
        "Snow",
        "Atmosphere",
        "Exreeme",
    ]:
        badDay[0] = True
        badDay[1].append(weatherData["weather"][0]["description"])
    elif weatherData["main"]["humidity"] > 80:
        badDay[0] = True
        badDay[1].append(weatherData["main"]["humidity"])
    if weatherData["main"]["temp_max"] > 27:
        badDay[0] = True
        badDay[1].append(weatherData["main"]["temp_max"])
    elif weatherData["main"]["temp_min"] < -5:
        badDay[0] = True
        badDay[1].append(weatherData["main"]["temp_min"])
    if weatherData["wind"]["speed"] > 10:
        badDay[0] = True
        badDay[1].append(weatherData["wind"]["speed"])

    logger.info("Speaking weather data:\n")
    # Speak the weather data
    greeting = ""
    random = ["Weather patterns ", "My scans "]
    greeting += random[randint(0, len(random) - 1)]

    # Time variables
    hour = strftime("%I", localtime())

    ampm = strftime("%p", localtime())

    producer = get_producer()
    if not producer:
        logger.error("No Kafka producer available, cannot speak weather")
        return False
    if badDay[0]:
        producer.send("speak", b"I am afraid I don't have good news.")
        greeting += "indicate "

        for i in range(len(badDay[1])):
            if badDay[1][i] == weatherData["weather"][0]["description"]:
                greeting += badDay[1][i]
            elif badDay[1][i] == weatherData["main"]["humidity"]:
                greeting += "humidity of a steam bath"
            elif badDay[1][i] == weatherData["main"]["temp_max"]:
                greeting += "it is too hot for my gentle circuits"
            elif badDay[1][i] == weatherData["main"]["temp_min"]:
                greeting += "it is catalysmically cold"
            elif badDay[1][i] == weatherData["wind"]["speed"]:
                greeting += "the wind will seriously ruin your hair"

            if len(badDay[1]) >= 2 and i < (len(badDay[1]) - 1):
                add = [
                    " , also, ",
                    " , and if that isn't enough, ",
                    " , and to make matters worse, ",
                ]
                greeting += add[randint(0, len(add) - 1)]
            elif len(badDay[1]) > 2 and i == (len(badDay[1]) - 1):
                greeting += " , and on top of everything, "
            else:
                logger.info(greeting + "\n")
        producer.send("speak", greeting.encode("utf-8"))
    else:
        producer.send("speak", b"Weather today is just gorgeous!")
        greeting += "indicate " + weatherData["weather"][0]["description"]
        producer.send("speak", greeting.encode("utf-8"))
        logger.info(greeting + "\n")

    producer.send(
        "speak",
        (
            "Current temperature in "
            + weatherData["name"]
            + " is "
            + str(int(weatherData["main"]["temp"]))
            + " degrees"
        ).encode("utf-8"),
    )
    if ampm == "AM" and int(hour) < 10:
        producer.send(
            "speak",
            (
                "Today's high is expected to be "
                + str(int(weatherData["main"]["temp_max"]))
                + " degrees"
            ).encode("utf-8"),
        )

    logger.info("Spoke weather\n")
    return True


def getWeather(lat, lon):
    """
    Fetches current weather data for the given latitude and longitude from the OpenWeatherMap API,
    updates the environment and routines tables in the database with the retrieved data, and
    communicates the weather conditions via Kafka messages for speech synthesis.

    The function performs the following steps:
    1. Retrieves the OpenWeatherMap API key from the database.
    2. Makes an API call to fetch weather data in metric units.
    3. Parses and logs detailed weather information including city, wind speed, pressure, humidity,
       temperature ranges, description, sunrise, and sunset times.
    4. Updates the environment table with weather details.
    5. Updates sunrise and sunset routines to trigger 30 minutes before the actual events.
    6. Evaluates weather conditions to determine if it's a "bad day" based on weather type,
       humidity (>80%), temperature extremes (>27°C or <-5°C), or wind speed (>10 m/s).
    7. Sends Kafka messages to speak the weather: announces bad conditions with specific reasons
       or good weather, followed by current temperature and optionally
       today's high if in the morning.

    Parameters:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.

    Returns:
        bool: True if the weather data was successfully fetched, parsed, and updated;
        False otherwise.
    """
    # connect to db
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()

    weatherData = parse_weather(cursor, lat, lon)
    if not weatherData:
        db.close()
        return False

    if not update_db_weather(db, cursor, weatherData):
        db.close()
        return False

    if not update_routines(db, cursor, weatherData):
        db.close()
        return False

    db.close()

    if not speak_weather(weatherData):
        return False

    return True


def KtoC(tempK):
    """
    converts temperature in kelvin to celsius
    """
    return math.trunc(int(tempK) - 273.15)


# purely for testing purposes
if __name__ == "__main__":
    getWeather(0.0, 0.0)
