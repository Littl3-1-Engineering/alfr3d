# Modified for containerization: logging to stdout instead of file
"""Main application for the ALFR3D user service, handling user management and state tracking."""
import os
import sys
import time
import logging

import json
import pymysql  # Changed from MySQLdb to pymysql
from kafka import KafkaConsumer, KafkaProducer
from datetime import datetime, timedelta, timezone

from db_utils import check_mute_optimized

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("UsersLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Changed to stream handler for container logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PSWD = os.environ["MYSQL_PSWD"]
MYSQL_DB = os.environ["MYSQL_NAME"]
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ALFR3D_ENV_NAME = os.environ["ALFR3D_ENV_NAME"]

producer = None
while producer is None:
    try:
        print("Connecting to Kafka at: " + KAFKA_URL)
        producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
        logger.info("Connected to Kafka")
    except Exception:
        logger.error("Failed to connect to Kafka, retrying in 5 seconds")
        time.sleep(5)


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
    if producer:
        event = {
            "id": f"user_{event_type}_{datetime.now(timezone.utc).isoformat()}",
            "type": event_type,
            "message": message,
            "time": datetime.now(timezone.utc).isoformat() + "Z",
        }
        try:
            producer.send("event-stream", json.dumps(event).encode("utf-8"))
            producer.flush()
            logger.info(f"Sent event: {event}")
        except Exception as e:
            logger.error(f"Failed to send event: {str(e)}")


class User:
    """
    User Class for Alfr3d Users
    """

    name = "unknown"
    state = "offline"
    last_online = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    userType = "guest"

    def create(self):
        logger.info("Creating a new user")
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()

        try:
            exists = self.get()
        except Exception:
            exists = False
        if exists:
            logger.error("User with that name already exists")
            db.close()
            return False

        logger.info("Creating a new DB entry for user: " + self.name)
        if self.last_online is None:
            self.last_online = datetime(1970, 1, 1)

        try:
            cursor.execute(
                """
                SELECT s.id as state_id, ut.id as type_id, e.id as env_id
                FROM states s, user_types ut, environment e
                WHERE s.state = 'offline' AND ut.type = 'guest' AND e.name = %s
                """,
                (ALFR3D_ENV_NAME,),
            )
            result = cursor.fetchone()
            if not result:
                logger.error("Failed to get lookup IDs")
                db.rollback()
                db.close()
                return False

            usrstate, usrtype, envid = result

            cursor.execute(
                "INSERT INTO user(username, last_online, created_at, state, type, environment_id) "
                "VALUES (%s, %s, NOW(), %s, %s, %s)",
                (self.name, self.last_online, usrstate, usrtype, envid),
            )
            db.commit()
        except Exception as e:
            logger.error("Failed to create a new entry in the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
        if not check_mute():
            producer.send("speak", b"A new user has been added to the database")
        else:
            send_event("info", "Speak request muted: A new user has been added to the database")
        event = {
            "id": f"user_created_{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "type": "success",
            "message": f"New user {self.name} created",
            "time": datetime.now(timezone.utc).isoformat(),
        }
        producer.send("event-stream", json.dumps(event).encode("utf-8"))
        return True

    def get(self):
        """
        Description:
            Find a user from DB by name
        """
        logger.info("Looking for user: " + self.name)
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from user WHERE username = %s", (self.name,))
        data = cursor.fetchone()

        if not data:
            logger.warning(
                "Failed to find user with username: " + self.name + " in the database"
            )
            db.close()
            return False

        # print data
        self.name = data[1]
        self.state = data[5]
        self.last_online = data[6]
        self.userType = data[8]

        db.close()
        return True

    def update(self):
        """
        Description:
            Update a User in DB
        """
        logger.info("Updating user: " + self.name)
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from user WHERE username = %s", (self.name,))
        data = cursor.fetchone()

        if not data:
            logger.warning("Failed to find user with username: " + self.name + " in the database")
            db.close()
            return False

        logger.info("User found")
        logger.debug(data)

        try:
            cursor.execute(
                "UPDATE user SET username = %s WHERE username = %s",
                (self.name, self.name),
            )
            cursor.execute(
                "UPDATE user SET last_online = %s WHERE username = %s",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), self.name),
            )
            cursor.execute("SELECT * from states WHERE state = %s", ("online",))
            data = cursor.fetchone()
            if not data:
                logger.error("Online state not found")
                db.rollback()
                db.close()
                return False

            cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            data = cursor.fetchone()
            if not data:
                logger.error("Environment not found")
                db.rollback()
                db.close()
                return False
            envid = data[0]
            cursor.execute(
                "UPDATE user SET environment_id = %s WHERE username = %s",
                (envid, self.name),
            )

            db.commit()
        except Exception as e:
            logger.error("Failed to update the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        logger.info("Updated user: " + self.name)
        return True

    def delete(self):
        """
        Description:
            Delete a User from DB
        """
        logger.info("Deleting a User")
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from user WHERE username = %s", (self.name,))
        data = cursor.fetchone()

        if not data:
            logger.warning(
                "Failed to find user with username: " + self.name + " in the database"
            )
            db.close()
            return False

        logger.info("User found")

        try:
            cursor.execute("DELETE from user WHERE username = %s", (self.name,))
            db.commit()
        except Exception as e:
            logger.error("Failed to update the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        logger.info("Deleted user with username: " + self.name)
        return True


def refresh_user_devices(user, cursor, db, env_id):
    """
    Updates the user's last_online timestamp based on the most recent device activity.
    """
    logger.info("Refreshing user devices for " + user[1])
    last_online = user[6]
    if user[6] is None:
        last_online = datetime(1970, 1, 1)

    try:
        logger.info("Fetching user devices")
        cursor.execute(
            "SELECT d.last_online FROM device d \
                        inner join device_types dt on d.device_type = dt.id \
                        WHERE user_id = "
            + str(user[0])
            + ' \
                        AND (type = "guest" or type = "resident");'
        )
        devices = cursor.fetchall()
        for device in devices:
            if device[0] and (device[0] > last_online):
                logger.info("Updating user " + user[1])
                cursor.execute(
                    "UPDATE user SET last_online = %s, environment_id = %s WHERE username = %s",
                    (str(device[0]), str(env_id), user[1]),
                )
                db.commit()
                last_online = device[0]
    except Exception as e:
        logger.error("Failed to update the database")
        logger.error("Traceback: " + str(e))
        db.rollback()
        raise  # Re-raise to handle in caller

    return last_online


def update_user_state(user, cursor, db, stat, producer, last_online):
    """
    Updates the user's state to online or offline based on last_online timestamp.
    Sends Kafka events for state changes.
    """
    try:
        time_now = datetime.now(timezone.utc)
        if last_online:
            delta = time_now - last_online.replace(tzinfo=timezone.utc)
        else:
            delta = timedelta(minutes=60)
    except Exception:
        logger.error("Failed to figure out the timedelta")
        delta = timedelta(minutes=60)

    if delta < timedelta(minutes=30):  # 30 minutes
        logger.info("User is online")
        if user[5] == stat["offline"]:
            logger.info(user[1] + " just came online")
            if not check_mute():
                producer.send("speak", bytes(user[1] + " just came online", "utf-8"))
            else:
                send_event("info", f"Speak request muted: {user[1]} just came online")
            cursor.execute(
                "UPDATE user SET state = %s WHERE username = %s",
                (stat["online"], user[1]),
            )
            logger.info(f"User {user[1]} state changed to online")
            cursor.execute("SELECT * FROM user_types where id = %s", (user[8],))
            usr_type = cursor.fetchone()
            if not usr_type:
                logger.error("User type not found")
                return
            speak_welcome(producer, user[1], usr_type[1], user[6])
            event = {
                "id": f"user_online_{user[1]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "info",
                "message": f"User {user[1]} came online",
                "time": datetime.now(timezone.utc).isoformat(),
            }
            producer.send("event-stream", json.dumps(event).encode("utf-8"))
    else:
        logger.info("User is offline")
        if user[5] == stat["online"]:
            logger.info(user[1] + " went offline")
            cursor.execute(
                "UPDATE user SET state = %s WHERE username = %s",
                (stat["offline"], user[1]),
            )
            logger.info(f"User {user[1]} state changed to offline")
            cursor.execute(
                "UPDATE device SET state = %s WHERE user_id = %s",
                (stat["offline"], user[0]),
            )
            event = {
                "id": f"user_offline_{user[1]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "warning",
                "message": f"User {user[1]} went offline",
                "time": datetime.now(timezone.utc).isoformat(),
            }
            producer.send("event-stream", json.dumps(event).encode("utf-8"))

    try:
        db.commit()
    except Exception:
        logger.error("Failed to update the database")
        db.rollback()
        db.close()
        raise


def speak_welcome(producer, user_name, user_type, last_online):
    """
    Speaks a welcome message to a user who just came online.
    Greeting varies by user type and time since last seen.
    """
    try:
        time_now = datetime.now(timezone.utc)
        if last_online:
            tz = last_online.tzinfo
            last_online_aware = (
                last_online.replace(tzinfo=timezone.utc) if tz is None else last_online
            )
            time_away = time_now - last_online_aware
        else:
            time_away = timedelta(days=365)
    except Exception:
        time_away = timedelta(days=1)

    time_away_hours = time_away.total_seconds() / 3600

    user_type_lower = user_type.lower() if user_type else "guest"

    if user_type_lower == "owner":
        base_greeting = f"Welcome home, {user_name}"
    elif user_type_lower == "resident":
        base_greeting = f"Hello {user_name}, welcome back"
    elif user_type_lower == "guest":
        base_greeting = f"Welcome {user_name}"
    else:
        base_greeting = f"Hello {user_name}"

    if time_away_hours >= 168:
        time_suffix = "Long time no see"
    elif time_away_hours >= 24:
        time_suffix = "It's been a while"
    elif time_away_hours >= 1:
        time_suffix = "Good to see you"
    else:
        time_suffix = None

    if time_suffix:
        full_greeting = f"{base_greeting}. {time_suffix}"
    else:
        full_greeting = base_greeting

    if not check_mute():
        producer.send("speak", full_greeting.encode("utf-8"))
    else:
        send_event("info", f"Speak request muted: {full_greeting}")


# refreshes state and last_online for all users
def refresh_all():
    """
    Refreshes the state and last_online timestamp for all users based on device activity.
    For each user, updates last_online to the most recent device last_online if newer,
    then sets the user state to online if last_online is within 30 minutes, otherwise offline.
    Sends Kafka events for state changes and updates associated devices when going offline.
    """
    logger.info("Refreshing users")

    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()
    cursor.execute("SELECT * from user;")
    user_data = cursor.fetchall()

    # figure out device types
    dev_types = {}
    cursor.execute("SELECT * FROM device_types;")
    types = cursor.fetchall()
    for type in types:
        dev_types[type[1]] = type[0]

    # figure out states
    stat = {}
    cursor.execute("SELECT * FROM states;")
    states = cursor.fetchall()
    for state in states:
        stat[state[1]] = state[0]

    # figure out environments
    env_id = None
    cursor.execute("SELECT * FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
    env_data = cursor.fetchone()
    if env_data:
        env_id = env_data[0]

    for user in user_data:
        logger.info("Refreshing user " + user[1])
        logger.debug(user)

        try:
            last_online = refresh_user_devices(user, cursor, db, env_id)
            update_user_state(user, cursor, db, stat, producer, last_online)
        except Exception:
            continue

    db.close()
    logger.info("Refreshed all users")
    return True


if __name__ == "__main__":
    # get all instructions from Kafka
    # topic: user
    logger.info("Starting Alfr3d's user service")
    consumer = None
    while consumer is None:
        try:
            consumer = KafkaConsumer(
                "user", bootstrap_servers=KAFKA_URL, auto_offset_reset="earliest"
            )
            logger.info("Connected to Kafka user topic")
        except Exception:
            logger.error("Failed to connect to Kafka user topic, retrying in 5 seconds")
        time.sleep(5)

    while True:
        for message in consumer:
            if message.value.decode("ascii") == "alfr3d-user.exit":
                logger.info("Received exit request. Stopping service.")
                sys.exit(1)
            if message.value.decode("ascii") == "refresh-all":
                refresh_all()
            if message.key:
                if message.key.decode("ascii") == "create":
                    usr = User()
                    usr.name = message.value.decode("ascii")
                    usr.create()
                if message.key.decode("ascii") == "delete":
                    usr = User()
                    usr.name = message.value.decode("ascii")
                    usr.delete()

            time.sleep(10)
