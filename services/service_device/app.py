# Adapted for containerization: logging to stdout, MySQLdb to pymysql
import os
import sys
import time
import logging
import json
import socket
import pymysql  # Changed from MySQLdb
import subprocess
import datetime
from kafka import KafkaConsumer, KafkaProducer
from datetime import datetime, timedelta

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("DevicesLog")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Changed to stream handler for container logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_DB = os.environ["MYSQL_NAME"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PSWD = os.environ["MYSQL_PSWD"]
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ALFR3D_ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

producer = None
while producer is None:
    try:
        producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
        logger.info("Connected to Kafka")
    except Exception:
        logger.error("Failed to connect to Kafka, retrying in 5 seconds")
        time.sleep(5)


class Device:
    """
    Device Class for Alfr3d Users' devices
    """

    name = "unknown"
    IP = "0.0.0.0"
    MAC = "00:00:00:00:00:00"
    state = "offline"
    last_online = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    environment = ALFR3D_ENV_NAME
    user = "unknown"
    deviceType = "guest"

    # mandatory to pass MAC for robustness
    def create(self, mac):
        """
        Description:
            Add new device to the database with default parameters
        """
        logger.info("Creating a new device")
        db = pymysql.connect(
            host=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PSWD,
            database=MYSQL_DB,
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from device WHERE MAC = %s", (mac,))
        data = cursor.fetchone()

        if data:
            logger.warning("device already exists.... aborting")
            db.close()
            return False

        logger.info("Creating a new DB entry for device with MAC: " + mac)
        db = pymysql.connect(
            host=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PSWD,
            database=MYSQL_DB,
        )
        cursor = db.cursor()
        try:
            cursor.execute("SELECT * from states WHERE state = %s", (self.state,))
            devstate_data = cursor.fetchone()
            if not devstate_data:
                logger.error("State not found")
                db.rollback()
                db.close()
                return False
            devstate = devstate_data[0]
            cursor.execute("SELECT * from device_types WHERE type = %s", (self.deviceType,))
            devtype_data = cursor.fetchone()
            if not devtype_data:
                logger.error("Device type not found")
                db.rollback()
                db.close()
                return False
            devtype = devtype_data[0]
            cursor.execute("SELECT * from user WHERE username = %s", (self.user,))
            usrid_data = cursor.fetchone()
            if not usrid_data:
                logger.error("User not found")
                db.rollback()
                db.close()
                return False
            usrid = usrid_data[0]
            cursor.execute("SELECT * from environment WHERE name = %s", (self.environment,))
            envid_data = cursor.fetchone()
            if not envid_data:
                logger.error("Environment not found")
                db.rollback()
                db.close()
                return False
            envid = envid_data[0]
            cursor.execute(
                "INSERT INTO device(name, IP, MAC, last_online, state, device_type, user_id, environment_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (self.name, self.IP, self.MAC, self.last_online, devstate, devtype, usrid, envid),
            )
            db.commit()
        except Exception as e:
            logger.error("Failed to create a new entry in the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        event = {
            "id": f"device_created_{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "type": "success",
            "message": f"New device {self.name} added to database",
            "time": datetime.now().strftime("%I:%M %p"),
        }
        producer.send("event-stream", json.dumps(event).encode("utf-8"))
        logger.info("Device created successfully")
        return True

    def get(self, mac):
        """
        Description:
            Find device from DB by MAC
        """
        logger.info("Looking for device with MAC: " + mac)
        db = pymysql.connect(
            host=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PSWD,
            database=MYSQL_DB,
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from device WHERE MAC = %s", (mac,))
        data = cursor.fetchone()

        if not data:
            logger.warning("Failed to find a device with MAC: " + self.MAC + " in the database")
            db.close()
            return False

        logger.info("Device found")
        logger.info(data)
        print(data)  # DEBUG

        self.name = data[1]
        self.IP = data[2]
        self.MAC = data[3]
        self.state = data[4]
        self.last_online = data[5]
        self.deviceType = data[6]
        # Get username from user_id
        cursor.execute("SELECT username FROM user WHERE id = %s", (data[7],))
        user_data = cursor.fetchone()
        self.user = user_data[0] if user_data else "unknown"
        self.environment = data[8]

        db.close()
        return True

    # update entire object in DB with latest values
    def update(self):
        """
        Description:
            Update a Device in DB
        """
        logger.info("Updating device")
        db = pymysql.connect(
            host=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PSWD,
            database=MYSQL_DB,
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from device WHERE MAC = %s", (self.MAC,))
        data = cursor.fetchone()

        if not data:
            logger.warn("Failed to find a device with MAC: " + self.MAC + " in the database")
            db.close()
            return False

        logger.info("Device found")
        logger.info(data)

        try:
            cursor.execute("SELECT * from states WHERE state = %s", ("online",))
            data = cursor.fetchone()
            if not data:
                logger.error("Online state not found")
                db.close()
                return False
            stateid = data[0]
            cursor.execute("SELECT * from environment WHERE name = %s", (ALFR3D_ENV_NAME,))
            data = cursor.fetchone()
            if not data:
                logger.error("Environment not found")
                db.close()
                return False
            envid = data[0]
            cursor.execute(
                "UPDATE device SET name = %s, IP = %s, last_online = %s, state = %s, environment_id = %s WHERE MAC = %s",
                (
                    self.name,
                    self.IP,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    stateid,
                    envid,
                    self.MAC,
                ),
            )

            db.commit()

            event = {
                "id": f"device_online_{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": "info",
                "message": f"Device {self.name} came online",
                "time": datetime.now().strftime("%I:%M %p"),
            }
            producer.send("event-stream", json.dumps(event).encode("utf-8"))
        except Exception as e:
            logger.error("Failed to update the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        logger.info("Updated device with MAC: " + self.MAC)
        return True

    # update entire object in DB with latest values
    def delete(self):
        """
        Description:
            Delete a Device from DB
        """
        logger.info("Deleting device")
        db = pymysql.connect(
            host=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PSWD,
            database=MYSQL_DB,
        )
        cursor = db.cursor()
        cursor.execute("SELECT * from device WHERE MAC = %s", (self.MAC,))
        data = cursor.fetchone()

        if not data:
            logger.warn("Failed to find a device with MAC: " + self.MAC + " in the database")
            db.close()
            return False

        logger.info("Device found")
        # logger.info(data)

        try:
            cursor.execute("DELETE from device WHERE MAC = %s", (self.MAC,))
            db.commit()
        except Exception as e:
            logger.error("Failed to update the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

        db.close()
        logger.info("Deleted device with MAC: " + self.MAC)
        return True


def checkLAN():
    """
    Description:
        This function checks who is on LAN
    """
    logger.info("Checking localnet for online devices")

    # temporary file for storing results of network scan
    netclientsfile = os.path.join(
        os.path.join(os.getcwd(), os.path.dirname(__file__)), "netclients.tmp"
    )

    # find out which devices are online
    os.system(
        "arp-scan --localnet > " + netclientsfile
    )  # Removed sudo, assuming container runs as root or privileged

    netClients = open(netclientsfile, "r")
    netClientsMACs = []
    netClientsIPs = []

    # parse MAC and IP addresses
    for line in netClients:
        print(line)
        if not line.startswith("192.") and not line.startswith("10."):
            continue
        ret = line.split("\t")
        # parse MAC addresses from arp-scan run
        netClientsMACs.append(ret[1])
        # parse IP addresses from arp-scan run
        netClientsIPs.append(ret[0])

    # clean up and parse MAC&IP info
    netClients2 = {}
    for i in range(len(netClientsMACs)):
        netClients2[netClientsMACs[i]] = netClientsIPs[i]

    # find who is online and
    # update DB status and last_online time
    for member in netClientsMACs:
        device = Device()
        exists = device.get(member)

        # try to find out device name
        name = None
        try:
            name = socket.gethostbyaddr(netClients2[member])[0]
            if name == "_gateway":
                name = None
        except socket.herror:
            logger.error("Couldn't resolve hostname for device with MAC: " + member)
            name = None
        except Exception as e:
            logger.error("Failed to find out hostname")
            logger.error("Traceback: " + str(e))

        # if device exists in the DB update it
        if exists:
            logger.info("Updating device with MAC: " + member)
            device.IP = netClients2[member]
            device.update()

        # otherwise, create and add it.
        else:
            logger.info("Creating a new DB entry for device with MAC: " + member)
            device.IP = netClients2[member]
            device.MAC = member
            if name:
                device.name = name
            device.create(member)

    # Check for devices that have been offline for more than 30 minutes and set them to offline
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()

    # Get state mappings
    stat = {}
    cursor.execute("SELECT * FROM states;")
    states = cursor.fetchall()
    for state in states:
        stat[state[1]] = state[0]

    # Get all devices
    cursor.execute("SELECT * FROM device;")
    devices = cursor.fetchall()

    time_now = datetime.now()
    for device in devices:
        last_online_str = device[5]
        try:
            # last_online = datetime.strptime(last_online_str, "%Y-%m-%d %H:%M:%S")
            last_online = last_online_str
            delta = time_now - last_online
            if delta > timedelta(minutes=30) and device[4] == stat["online"]:
                logger.info("Setting device " + device[3] + " to offline due to inactivity")
                cursor.execute(
                    "UPDATE device SET state = %s WHERE MAC = %s", (stat["offline"], device[3])
                )
                db.commit()

                event = {
                    "id": f"device_offline_{device[3]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "type": "warning",
                    "message": f"Device {device[3]} went offline due to inactivity",
                    "time": datetime.now().strftime("%I:%M %p"),
                }
                producer.send("event-stream", json.dumps(event).encode("utf-8"))
        except Exception:
            logger.error("Error checking device offline status")

    db.close()

    logger.info("Cleaning up temporary files")
    os.system("rm -rf " + netclientsfile)

    producer.send("user", b"refresh-all")


if __name__ == "__main__":
    # get all instructions from Kafka
    # topic: device
    logger.info("Starting Alfr3d's device service")
    consumer = None
    while consumer is None:
        try:
            consumer = KafkaConsumer("device", bootstrap_servers=KAFKA_URL)
            logger.info("Connected to Kafka device topic")
        except Exception:
            logger.error("Failed to connect to Kafka device topic, retrying in 5 seconds")
            time.sleep(5)

    while True:
        for message in consumer:
            if message.value.decode("ascii") == "alfr3d-device.exit":
                logger.info("Received exit request. Stopping service.")
                sys.exit(1)
            if message.value.decode("ascii") == "scan net":
                checkLAN()

            time.sleep(10)
