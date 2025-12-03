# Adapted for containerization: logging to stdout, MySQLdb to pymysql
"""Main application for the ALFR3D device service, managing device tracking and network scanning."""
import os
import sys
import time
import logging
import json
import socket
import pymysql  # Changed from MySQLdb
from kafka import KafkaConsumer, KafkaProducer
from datetime import datetime, timedelta, timezone
from typing import Optional

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("DevicesLog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
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
                "INSERT INTO device(name, IP, MAC, last_online, state, device_type, user_id, "
                "environment_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    self.name,
                    self.IP,
                    self.MAC,
                    self.last_online,
                    devstate,
                    devtype,
                    usrid,
                    envid,
                ),
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
            "time": datetime.now(timezone.utc).isoformat(),
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
        logger.debug(data)
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
        logger.debug(data)

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
                "UPDATE device SET name = %s, IP = %s, last_online = %s, state = %s, "
                "environment_id = %s WHERE MAC = %s",
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

            # event = {
            #     "id": f"device_online_{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            #     "type": "info",
            #     "message": f"Device {self.name} came online",
            #     "time": datetime.now().strftime("%I:%M %p"),
            # }
            # producer.send("event-stream", json.dumps(event).encode("utf-8"))
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
        # logger.debug(data)

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


def resolve_hostname(ip: str) -> Optional[str]:
    """
    Resolve hostname for a given IP address.
    """
    try:
        name = socket.gethostbyaddr(ip)[0]
        if name == "_gateway":
            return None
        return name
    except socket.herror:
        logger.error("Couldn't resolve hostname for IP: " + ip)
        return None
    except Exception as e:
        logger.error("Failed to resolve hostname")
        logger.error("Traceback: " + str(e))
        return None


def update_or_create_device(mac: str, ip: str, name: Optional[str]) -> str:
    """
    Update existing device or create new one in DB.
    """
    device = Device()
    exists = device.get(mac)

    if exists:
        logger.info("Updating device with MAC: " + mac)
        device.IP = ip
        device.update()
        return "updated"
    else:
        logger.info("Creating a new DB entry for device with MAC: " + mac)
        device.IP = ip
        device.MAC = mac
        if name:
            device.name = name
        device.create(mac)
        return "created"


def check_offline_devices():
    """
    Check for devices offline for more than 30 minutes and mark them offline.
    """
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
            last_online = last_online_str
            delta = time_now - last_online
            if delta > timedelta(minutes=30) and device[4] == stat["online"]:
                logger.info("Setting device " + device[3] + " to offline due to inactivity")
                cursor.execute(
                    "UPDATE device SET state = %s WHERE MAC = %s",
                    (stat["offline"], device[3]),
                )
                db.commit()

                # event = {
                #     "id": f"device_offline_{device[3]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                #     "type": "warning",
                #     "message": f"Device {device[3]} went offline due to inactivity",
                #     "time": datetime.now().strftime("%I:%M %p"),
                # }
                # producer.send("event-stream", json.dumps(event).encode("utf-8"))
        except Exception:
            logger.error("Error checking device offline status")

    db.close()


def check_lan():
    """
    Scans the local network for online devices using ARP, updates the database with device
    information, and marks devices as offline if they haven't been seen for more than 30 minutes.

    ARP Scan Logic:
    - Executes 'arp-scan --localnet' to perform an ARP scan on the local network.
    - Saves the scan results to a temporary file 'netclients.tmp'.
    - Parses the output to extract IP and MAC addresses from lines starting with '192.' or '10.'.

    Parsing:
    - Splits each relevant line by tab to separate IP and MAC.
    - Builds a dictionary mapping MAC addresses to IP addresses.
    - Attempts to resolve hostnames using socket.gethostbyaddr for each IP.

    DB Updates:
    - For each discovered MAC, checks if the device exists in the database.
    - If the device exists, updates its IP address and last_online timestamp, setting state to
      'online'.
    - If the device does not exist, creates a new device entry with the MAC, IP, and
      resolved hostname (if available).
    - Sends Kafka events for device creation or coming online.

    Offline Checks:
    - Queries all devices in the database.
    - For devices marked as 'online', checks if the last_online time is more than 30 minutes ago.
    - If so, updates the device state to 'offline' and sends a Kafka event.
    - Cleans up the temporary scan file and triggers a 'refresh-all' Kafka message.
    """
    logger.info("Checking localnet for online devices")

    created_count = 0
    updated_count = 0

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

    # find who is online and update DB status and last_online time
    for member in netClientsMACs:
        ip = netClients2[member]
        name = resolve_hostname(ip)
        action = update_or_create_device(member, ip, name)
        if action == "created":
            created_count += 1
        elif action == "updated":
            updated_count += 1

    logger.info(f"Created {created_count} devices, updated {updated_count} devices.")

    check_offline_devices()

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
                check_lan()

            time.sleep(10)
