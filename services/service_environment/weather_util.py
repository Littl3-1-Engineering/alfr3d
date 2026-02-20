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
from kafka.errors import KafkaError
from time import strftime, localtime  # needed to obtain time
from datetime import datetime, timedelta
from urllib.request import urlopen  # used to make calls to www
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from random import randint
from db_utils import check_mute_optimized

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("WeatherLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
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


def check_mute() -> bool:
    """
    Description:
             checks what time it is and decides if Alfr3d should be quiet
             - between wake-up time and bedtime
             - only when Athos is at home
             - only when 'owner' is at home
    """
    return check_mute_optimized(ALFR3D_ENV_NAME)


def send_event(event_type, message):
    """Send event to event-stream topic"""
    p = get_producer()
    if p:
        event = {
            "id": f"weather_{event_type}_{datetime.now().isoformat()}",
            "type": event_type,
            "message": message,
            "time": datetime.now().isoformat() + "Z",
        }
        try:
            p.send("event-stream", json.dumps(event).encode("utf-8"))
            p.flush()
            logger.info(f"Sent event: {event}")
        except Exception as e:
            logger.error(f"Failed to send event: {str(e)}")


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
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if "appid" in query_params:
            del query_params["appid"]
        sanitized_query = urlencode(query_params, doseq=True)
        sanitized_url = urlunparse(parsed_url._replace(query=sanitized_query))
        logger.error("URL: " + sanitized_url)
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
    logger.info("Description:                    " + str(weatherData["weather"][0]["description"]))
    logger.info("Current Temperature:            " + str(weatherData["main"]["temp"]))
    logger.info(
        "Sunrise:                        "
        + datetime.fromtimestamp(weatherData["sys"]["sunrise"]).strftime("%Y-%m-%d %H:%M:%S")
    )
    logger.info(
        "Sunset:                         "
        + datetime.fromtimestamp(weatherData["sys"]["sunset"]).strftime("%Y-%m-%d %H:%M:%S")
    )
    logger.info("Parsed weather data\n")

    subjective_feel = determine_subjective_feel(weatherData)
    weatherData["subjective_feel"] = subjective_feel

    # Get timezone offset in seconds
    weatherData["timezone"] = weatherData.get("timezone", 0)

    return weatherData


def update_db_weather(db, cursor, weatherData):
    logger.info("Updating weather data in DB")

    try:
        cursor.execute(
            "UPDATE environment SET description = %s, low = %s, high = %s, sunrise = %s, "
            "sunset = %s, pressure = %s, humidity = %s, subjective_feel = %s, timezone = %s "
            "WHERE name = %s",
            (
                str(weatherData["weather"][0]["description"]),
                int(weatherData["main"]["temp_min"]),
                int(weatherData["main"]["temp_max"]),
                datetime.fromtimestamp(weatherData["sys"]["sunrise"]).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.fromtimestamp(weatherData["sys"]["sunset"]).strftime("%Y-%m-%d %H:%M:%S"),
                int(weatherData["main"]["pressure"]),
                int(weatherData["main"]["humidity"]),
                weatherData["subjective_feel"],
                weatherData["timezone"],
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
        sunrise_trig = datetime.fromtimestamp(weatherData["sys"]["sunrise"]) - timedelta(
            hours=0, minutes=30
        )
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


def determine_subjective_feel(weatherData):
    temp = weatherData["main"]["temp"]
    humidity = weatherData["main"]["humidity"]
    wind_kmh = weatherData["wind"]["speed"] * 3.6

    # Extremely cold
    if temp < -20:
        return "Extremely cold"
    # Very cold
    if -10 <= temp < 0:
        return "Very cold"
    # Cold
    if 0 <= temp < 10 and wind_kmh < 30:
        return "Cold"
    # Cool
    if 10 <= temp < 14 and wind_kmh < 20:
        return "Cool"
    # Perfect / Great day
    if 20 <= temp <= 25 and 40 <= humidity <= 60 and wind_kmh < 15:
        return "Perfect / Great day"
    # Very pleasant
    if ((17 <= temp <= 20) or (25 <= temp <= 28)) and 30 <= humidity <= 70 and wind_kmh < 20:
        return "Very pleasant"
    # Pleasant / Nice
    if ((14 <= temp <= 17) or (28 <= temp <= 30)) and 30 <= humidity <= 70 and wind_kmh < 25:
        return "Pleasant / Nice"
    # Warm
    if 28 <= temp <= 32 and humidity < 70:
        return "Warm"
    # Hot
    if 32 <= temp <= 36 and wind_kmh < 20:
        return "Hot"
    # Very hot
    if 36 <= temp <= 40:
        return "Very hot"
    # Extremely hot
    if temp > 40:
        return "Extremely hot"
    # Oppressively humid
    if temp >= 28 and humidity >= 70:
        return "Oppressively humid"
    # Very humid / Muggy
    if temp >= 24 and humidity >= 75 and wind_kmh < 15:
        return "Very humid / Muggy"
    # Windy (unpleasant)
    if wind_kmh > 40:
        return "Windy (unpleasant)"
    # Bad weather
    weather_main = weatherData["weather"][0]["main"]
    if weather_main in ["Thunderstorm", "Drizzle", "Rain", "Snow", "Atmosphere"]:
        return "Bad weather: " + weather_main.lower()
    # Default
    return "Neutral"


def speak_weather(db, cursor, weatherData):
    subjective_weather = weatherData["subjective_feel"]
    bad_categories = [
        "Extremely cold",
        "Very cold",
        "Cold",
        "Extremely hot",
        "Very hot",
        "Hot",
        "Oppressively humid",
        "Very humid / Muggy",
        "Windy (unpleasant)",
    ]
    badDay = [subjective_weather in bad_categories, []]

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
        if not check_mute():
            producer.send("speak", b"I am afraid I don't have good news.")
        else:
            send_event("info", "Speak request muted: I am afraid I don't have good news.")
        greeting += "indicate " + subjective_weather
        if not check_mute():
            producer.send("speak", greeting.encode("utf-8"))
        else:
            send_event("info", f"Speak request muted: {greeting}")
    else:
        if not check_mute():
            producer.send("speak", b"Weather today is just gorgeous!")
        else:
            send_event("info", "Speak request muted: Weather today is just gorgeous!")
        greeting += "indicate " + weatherData["weather"][0]["description"]
        if not check_mute():
            producer.send("speak", greeting.encode("utf-8"))
        else:
            send_event("info", f"Speak request muted: {greeting}")
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


def get_weather(lat, lon):
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

    if not speak_weather(db, cursor, weatherData):
        db.close()
        return False
    db.close()
    return True


def kto_c(tempK):
    """
    converts temperature in kelvin to celsius
    """
    return math.trunc(int(tempK) - 273.15)


# purely for testing purposes
if __name__ == "__main__":
    get_weather(0.0, 0.0)
