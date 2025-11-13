# Adapted for containerization: logging to stdout, MySQLdb to pymysql
import os
import re
import sys
import time
import socket
import json
import logging
import weather_util
import pymysql  # Changed from MySQLdb
from kafka import KafkaConsumer, KafkaProducer
from urllib.request import urlopen


# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("EnvironmentLog")
logger.setLevel(logging.DEBUG)
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
        except Exception as e:
            logger.error("Failed to connect to Kafka")
            return None
    return producer


# def checkLocation(method="freegeoip", speaker=None):
def checkLocation(method="freegeoip"):
    """
    Check location based on IP
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

    country = "unknown"
    state = "unknown"
    city = "unknown"
    ip = "unknown"

    try:
        cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        data = cursor.fetchone()

        if data:
            logger.info("Found environment configuration for this host")
            print(data)
            country = data[6]
            state = data[5]
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
                return [False, 0, 0]
    except Exception:
        logger.error("Environment check failed")
        p = get_producer()
        if p:
            p.send("speak", b"Environment check failed")
            p.flush()

    # placeholders for my ip
    myipv4 = None
    myipv6 = None

    # get my current ip
    logger.info("Getting my IP")
    try:
        myipv4 = urlopen("http://ifconfig.me/ip").read().decode("ascii")
        logger.info("My IP: " + myipv4)
    except Exception as e:
        logger.error("Error getting my IPV4")
        myipv4 = None
        logger.error("Traceback " + str(e))
        logger.info("Trying to get our IPV6")
        try:
            myipv6 = urlopen("http://ipv6bot.whatismyipaddress.com").read()
        except Exception as e:
            logger.error("Error getting my IPV6")
            logger.error("Traceback " + str(e))
    finally:
        if not myipv6 and not myipv4:
            return [False, 0, 0]

    # get our geocoding info
    country_new = country
    state_new = state
    city_new = city
    ip_new = ip
    lat_new = "n/a"
    long_new = "n/a"

    if method == "dbip":
        logger.info("getting API key for db-ip from DB")
        cursor.execute("SELECT * from config WHERE name = %s", ("dbip",))
        data = cursor.fetchone()

        if data:
            logger.info("Found API key")
            print(data)  # DEBUG
            apikey = data[2]
        else:
            logger.warning("Failed to get API key for dbip")

        # get my geo info
        if myipv6:
            url6 = "http://api.db-ip.com/addrinfo?addr=" + myipv6 + "&api_key=" + apikey
        elif myipv4:
            url4 = "http://api.db-ip.com/addrinfo?addr=" + myipv4 + "&api_key=" + apikey

        logger.info("Getting my location")
        try:
            # try to get our info based on IPV4
            info4 = json.loads(urlopen(url4).read().decode("utf-8"))
            print(info4)  # DEBUG

            if info4["city"]:
                country_new = info4["country"]
                state_new = info4["stateprov"]
                city_new = info4["city"]
                ip_new = info4["address"]

            # if that fails, try the IPV6 way
            else:
                info6 = json.loads(urlopen(url6).read().decode("utf-8"))
                print(info6)  # DEBUG

                if info6["country"]:
                    country_new = info6["country"]
                    state_new = info6["stateprov"]
                    city_new = info6["city"]
                    ip_new = info6["address"]

                else:
                    raise Exception("Unable to get geo info based on IP")

        except Exception as e:
            logger.error("Error getting my location:" + e)
            return [False, 0, 0]

    elif method == "freegeoip":
        # get API key for ipstack which was freegeoip.net
        logger.info("getting API key for ipstack from DB")
        cursor.execute("SELECT * from config WHERE name = %s", ("ipstack",))
        data = cursor.fetchone()

        if data:
            logger.info("Found API key")
            print(data)  # DEBUG
            apikey = data[2]
        else:
            logger.warning("Failed to get API key for ipstack")

        if myipv4:
            # url4 = "http://freegeoip.net/json/"+myipv4
            url4 = "http://api.ipstack.com/" + myipv4 + "?access_key=" + apikey

            try:
                # try to get our info based on IPV4
                info4 = json.loads(urlopen(url4).read().decode("utf-8"))
                print(info4)  # DEBUG
                if info4["city"]:
                    country_new = info4["country_name"]
                    # state_new = info4['stateprov_name']
                    city_new = info4["city"]
                    ip_new = info4["ip"]
                    lat_new = info4["latitude"]
                    long_new = info4["longitude"]

                else:
                    raise Exception("Unable to get geo info based on IP")

            except Exception as e:
                logger.error("Error getting my location:" + str(e))
                return [False, 0, 0]

    else:
        logger.warning("Unable to obtain geo info - invalid method specified")
        return [False, 0, 0]

    # by this point we got our geo info
    # just gotta clean it up because sometimes we get garbage in the city name
    city_new = re.sub("[^A-Za-z]+", "", city_new)
    if state_new:
        state_new = state_new.strip()
    else:
        state_new = country_new

    logger.info("IP: " + str(ip_new))
    logger.info("City: " + str(city_new))
    logger.info("State/Prov: " + str(state_new))
    logger.info("Country: " + str(country_new))
    logger.info("Longitude: " + str(long_new))
    logger.info("Latitude: " + str(lat_new))

    if city_new == city:
        logger.info("You are still in the same location")
        p = get_producer()
        if p:
            p.send("speak", b"It would appear that I am in the same location as the last time")
    else:
        logger.info("Oh hello! Welcome to " + city_new)
        p = get_producer()
        if p:
            p.send("speak", b"Welcome to " + city_new.encode("utf-8") + b" sir")
            p.send("speak", b"I trust you enjoyed your travels")

        try:
            cursor.execute(
                "UPDATE environment SET country = %s, state = %s, city = %s, IP = %s, latitude = %s, longitude = %s WHERE name = %s",
                (country_new, state_new, city_new, ip_new, lat_new, long_new, ALFR3D_ENV_NAME),
            )
            db.commit()
            logger.info("Environment updated")
        except Exception:
            logger.error("Failed to update Environment database")
            db.rollback()
            db.close()
            return [False, 0, 0]

    db.close()

    # get latest weather info for new location
    try:
        logger.info("Getting latest weather")
        weather_util.getWeather(lat_new, long_new)
    except Exception as e:
        logger.error("Failed to get weather")
        logger.error("Traceback " + str(e))
    return


def checkWeather():
    logger.info("Checking latest weather reports")
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()

    cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
    data = cursor.fetchone()

    if data and data[2] and data[3]:
        weather_util.getWeather(data[2], data[3])
    else:
        logger.warning("No location data available for weather check")


# Main
if __name__ == "__main__":
    # get all instructions from Kafka
    # topic: environment
    consumer = None
    while consumer is None:
        try:
            consumer = KafkaConsumer("environment", bootstrap_servers=KAFKA_URL)
            logger.info("Connected to Kafka environment topic")
        except Exception:
            logger.error("Failed to connect to Kafka environment topic, retrying in 5 seconds")
            time.sleep(5)

    while True:
        for message in consumer:
            msg = message.value.decode("ascii")
            print(f"Received Kafka message: {msg}")
            if msg == "alfr3d-env.exit":
                logger.info("Received exit request. Stopping service.")
                sys.exit()
            if msg == "check location":
                checkLocation()
            if msg == "check weather":
                checkWeather()

            time.sleep(10)
