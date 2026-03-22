# Adapted for containerization: logging to stdout, MySQLdb to pymysql
"""Main module for the ALFR3D environment service, handling location detection and
weather updates."""
# Standard libraries
import os
import re
import sys
import socket
import orjson
import logging
import threading
import datetime
from datetime import timezone
from urllib.request import urlopen

shutdown_event = threading.Event()

# Third-party libraries
import pymysql  # Changed from MySQLdb  # noqa: E402
from kafka import KafkaConsumer  # noqa: E402
from kafka.errors import KafkaError  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer, get_kafka_url, db_utils  # noqa: E402

import weather_util  # noqa: E402

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("EnvironmentLog")
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
ALFR3D_ENV_NAME = os.environ.get("ALFR3D_ENV_NAME", socket.gethostname())


def check_mute() -> bool:
    """
    Description:
             checks what time it is and decides if Alfr3d should be quiet
             - between wake-up time and bedtime
             - only when Athos is at home
             - only when 'owner' is at home
    """
    return db_utils.check_mute_optimized(ALFR3D_ENV_NAME)


def send_event(event_type, message):
    """Send event to event-stream topic"""
    p = get_producer()
    if p:
        event = {
            "id": f"environment_{event_type}_{datetime.datetime.now(timezone.utc).isoformat()}",
            "type": event_type,
            "message": message,
            "time": datetime.datetime.now(timezone.utc).isoformat() + "Z",
        }
        try:
            p.send("event-stream", orjson.dumps(event))
            p.flush()
            logger.info(f"Sent event: {event}")
        except KafkaError as e:
            logger.error(f"Kafka error sending event: {e}")
        except Exception as e:
            logger.error(f"Failed to send event: {e}")


def get_ip():
    myipv4 = None
    myipv6 = None
    try:
        myipv4 = urlopen("http://ifconfig.me/ip").read().decode("ascii")
        logger.info("My IP: " + myipv4)
    except OSError as e:
        logger.error(f"Error getting my IPV4: {e}")
        myipv4 = None
        logger.info("Trying to get our IPV6")
        try:
            myipv6 = urlopen("http://ipv6bot.whatismyipaddress.com").read().decode("ascii")
        except OSError as e:
            logger.error(f"Error getting my IPV6: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting IP: {e}")
    return myipv4, myipv6


def geocode_ip(myipv4, myipv6, method, cursor):
    if method == "dbip":
        cursor.execute("SELECT * from config WHERE name = %s", ("dbip",))
        data = cursor.fetchone()
        if data and len(data) > 15 and data[15] == 1:
            logger.info("Manual override active, skipping auto location update")
            return None
        apikey = data[2] if data else None
        if not apikey:
            logger.warning("Failed to get API key for dbip")
            return None
        try:
            if myipv4:
                url = "http://api.db-ip.com/addrinfo?addr=" + myipv4 + "&api_key=" + apikey
                info = orjson.loads(urlopen(url).read())
                if info.get("city"):
                    return {
                        "country": info["country"],
                        "state": info["stateprov"],
                        "city": info["city"],
                        "ip": info["address"],
                        "lat": "n/a",
                        "long": "n/a",
                    }
            if myipv6:
                url = "http://api.db-ip.com/addrinfo?addr=" + myipv6 + "&api_key=" + apikey
                info = orjson.loads(urlopen(url).read())
                if info.get("country"):
                    return {
                        "country": info["country"],
                        "state": info["stateprov"],
                        "city": info["city"],
                        "ip": info["address"],
                        "lat": "n/a",
                        "long": "n/a",
                    }
            return None
        except Exception as e:
            logger.error("Error getting my location:" + str(e))
            return None
    elif method == "freegeoip":
        cursor.execute("SELECT * from config WHERE name = %s", ("ipstack",))
        data = cursor.fetchone()
        if data and len(data) > 15 and data[15] == 1:
            logger.info("Manual override active, skipping auto location update")
            return None
        apikey = data[2] if data else None
        if not apikey:
            logger.warning("Failed to get API key for ipstack")
            return None
        if myipv4:
            url = "http://api.ipstack.com/" + myipv4 + "?access_key=" + apikey
            try:
                info = orjson.loads(urlopen(url).read())
                if info.get("city"):
                    return {
                        "country": info["country_name"],
                        "state": info.get("region_name", ""),
                        "city": info["city"],
                        "ip": info["ip"],
                        "lat": info["latitude"],
                        "long": info["longitude"],
                    }
                else:
                    return None
            except Exception as e:
                logger.error("Error getting my location:" + str(e))
                return None
        else:
            return None
    else:
        return None


def update_db(new_data, existing_city, cursor, db, producer):
    if not new_data:
        return False
    city_new = re.sub("[^A-Za-z]+", "", new_data["city"])
    state_new = new_data["state"].strip() if new_data["state"] else new_data["country"]
    country_new = new_data["country"]
    ip_new = new_data["ip"]
    lat_new = new_data["lat"]
    long_new = new_data["long"]
    logger.debug("IP: " + str(ip_new))
    logger.debug("City: " + str(city_new))
    logger.info("State/Prov: " + str(state_new))
    logger.info("Country: " + str(country_new))
    logger.info("Longitude: " + str(long_new))
    logger.info("Latitude: " + str(lat_new))
    if city_new == existing_city:
        logger.info("You are still in the same location")
        if producer:
            producer.send(
                "speak",
                b"It would appear that I am in the same location as the last time",
            )
            producer.flush()
    else:
        logger.info("Oh hello! Welcome to " + city_new)
        if producer:
            if not check_mute():
                producer.send("speak", b"Welcome to " + city_new.encode("utf-8") + b" sir")
                producer.send("speak", b"I trust you enjoyed your travels")
            else:
                send_event("info", f"Speak request muted: Welcome to {city_new}")
                send_event("info", "Speak request muted: I trust you enjoyed your travels")
            producer.flush()
        try:
            cursor.execute(
                "UPDATE environment SET country = %s, state = %s, city = %s, IP = %s, "
                "latitude = %s, longitude = %s WHERE name = %s",
                (
                    country_new,
                    state_new,
                    city_new,
                    ip_new,
                    lat_new,
                    long_new,
                    ALFR3D_ENV_NAME,
                ),
            )
            db.commit()
            logger.info("Environment updated")
        except Exception:
            logger.error("Failed to update Environment database")
            db.rollback()
            return False
    return True


# def check_location(method="freegeoip", speaker=None):
def check_location(method="freegeoip"):
    """
    Performs geocoding to determine the current location based on the device's IP address.

    The geocoding flow involves the following steps:
    1. Checks the database for a manual location override flag. If active, skips auto-update and
       returns early.
    2. Retrieves existing location data (country, state, city) from the database for the current
       environment name. If no data exists, creates a new environment entry in the database.
    3. Fetches the current public IP address (IPv4 first, falls back to IPv6 if necessary)
       using external services.
    4. Depending on the specified method ("dbip" or "freegeoip"):
       - Retrieves the corresponding API key from the database.
       - Checks for a manual override flag for the API key; if active, skips update.
       - Constructs the API URL with the IP address and API key.
       - Sends a request to the geocoding API and parses the JSON response.
       - Extracts location details: country, state/province, city, IP, latitude, and longitude.
     5. Cleans up the retrieved data (e.g., removes non-alphabetic characters from city names).
      6. Compares the new location with the existing one. If different, updates the database and
         sends welcome messages via Kafka.
     7. Triggers a weather update for the new location using the latitude and longitude.
     8. Returns a status indicating success or failure.

    Args:
        method (str): The geocoding method to use. Supported values are "dbip" and "freegeoip".
        Defaults to "freegeoip".

    Returns:
        None: The function does not return a value but updates the database and sends Kafka
        messages.
    """
    logger.info("Checking environment info")
    p = get_producer()
    if p:
        p.send("speak", b"Checking environment info")
        p.flush()
    # get latest DB environment info
    # Initialize the database
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()

    city = "unknown"

    cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
    data = cursor.fetchone()
    if data and len(data) > 16 and data[16] == 1:
        logger.info("Manual location override active, skipping auto location update")
        db.close()
        return [True, 0, 0]

    if data:
        logger.info("Found environment configuration for this host")

        if len(data) > 4:
            city = data[4]
    else:
        logger.warning("Failed to find environment configuration for this host")
        logger.info("Creating environment configuration for this host")
        try:
            cursor.execute("INSERT INTO environment (name) VALUES (%s)", (ALFR3D_ENV_NAME,))
            db.commit()
            logger.info("New environment created")
        except Exception:
            logger.error("Failed to add new environment to DB")
            db.rollback()
            db.close()
            logger.error("Environment check failed")
            p = get_producer()
            if p:
                p.send("speak", b"Environment check failed")
                p.flush()
            return [False, 0, 0]

    myipv4, myipv6 = get_ip()
    if not myipv4 and not myipv6:
        db.close()
        return [False, 0, 0]

    new_data = geocode_ip(myipv4, myipv6, method, cursor)
    if not new_data:
        db.close()
        return [False, 0, 0]

    success = update_db(new_data, city, cursor, db, p)
    if not success:
        db.close()
        return [False, 0, 0]

    db.close()

    # get latest weather info for new location
    # try:
    #     logger.info("Getting latest weather")
    #     weather_util.get_weather(new_data["lat"], new_data["long"])
    # except Exception as e:
    #     logger.error("Failed to get weather")
    #     logger.error("Traceback " + str(e))
    return


def check_weather():
    logger.info("Checking latest weather reports")
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()

    cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
    data = cursor.fetchone()

    if data and data[2] and data[3]:
        weather_util.get_weather(data[2], data[3])
    else:
        logger.warning("No location data available for weather check")


# Main
if __name__ == "__main__":
    logger.info("Starting Alfr3d's environment service")
    consumer = None
    retry_count = 0
    while consumer is None and not shutdown_event.is_set():
        try:
            consumer = KafkaConsumer("environment", bootstrap_servers=get_kafka_url())
            logger.info("Connected to Kafka environment topic")
        except Exception:
            retry_count += 1
            wait_time = min(5 * (2 ** (retry_count - 1)), 60)
            logger.error(
                f"Failed to connect to Kafka environment topic, " f"retrying in {wait_time} seconds"
            )
            shutdown_event.wait(wait_time)

    if shutdown_event.is_set():
        logger.info("Shutdown requested during connection attempt")
        sys.exit(0)

    while not shutdown_event.is_set():
        messages = consumer.poll(timeout_ms=1000)
        for topic_partition, msgs in messages.items():
            for message in msgs:
                msg = message.value.decode("ascii")
                print(f"Received Kafka message: {msg}")
                if msg == "alfr3d-env.exit":
                    logger.info("Received exit request. Stopping service.")
                    shutdown_event.set()
                    break
                if msg == "check location":
                    check_location()
                if msg == "check weather":
                    check_weather()
