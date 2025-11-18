# Modified for containerization: logging to stdout instead of file
"""REST API service for ALFR3D, providing endpoints for users, devices, containers, and events."""
import os
import sys
import logging
import subprocess
import json
import pymysql  # Changed from MySQLdb to pymysql
import threading
from kafka import KafkaConsumer, TopicPartition
from kafka.errors import KafkaError
from flask import Flask, request, jsonify, Response
from typing import Dict, Any, Optional, List
from flask_cors import CORS

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("ApiLog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
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

# Store recent events
recent_events = []
recent_sa = []


def consume_events() -> None:
    """Consume events from Kafka event-stream topic and store recent events."""
    try:
        logger.info(f"Event consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "event-stream", bootstrap_servers=KAFKA_URL, auto_offset_reset="latest"
        )
        logger.info("Connected to Kafka event-stream topic")
        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        logger.info("Polling for event message")
                        try:
                            data = json.loads(message.value.decode("utf-8"))
                            if isinstance(data, list):
                                recent_events.extend(data)
                            else:
                                recent_events.append(data)
                            # Keep only the most recent 20 events
                            recent_events[:] = recent_events[-20:]
                            logger.info(f"Received events: {data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Error processing event message: {str(e)}")
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for events: {str(e)}")


def consume_sa() -> None:
    """Consume SA from Kafka situational-awareness topic and store recent SA."""
    try:
        logger.info(f"SA consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "situational-awareness",
            bootstrap_servers=KAFKA_URL,
            auto_offset_reset="latest",
        )
        logger.info("Connected to Kafka situational-awareness topic")
        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        logger.info("Polling for SA message")
                        try:
                            data = json.loads(message.value.decode("utf-8"))
                            recent_sa.clear()
                            if isinstance(data, list):
                                recent_sa.extend(data)
                            else:
                                recent_sa.append(data)
                            logger.info(f"Received SA: {data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Error processing SA message: {str(e)}")
    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for SA: {str(e)}")


# Check if Docker is available via subprocess
docker_available = False
try:
    # Set environment for docker commands
    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"

    result = subprocess.run(
        ["docker", "version"], capture_output=True, text=True, timeout=5, env=env
    )
    if result.returncode == 0:
        docker_available = True
        logger.info("Docker CLI is available via socket")
    else:
        logger.warning("Docker CLI not available")
except subprocess.SubprocessError as e:
    logger.warning(f"Docker check failed: {str(e)}")

# Flask API
app = Flask(__name__)
CORS(app)


@app.route("/api/users")
def get_users():
    """
    Retrieve list of users, optionally filtered by online status.

    Query Parameters:
        online (str): If 'true', return only online users. Defaults to 'false'.

    Returns:
        JSON: List of user dictionaries with id, name, email, about_me, state, type, last_online.
    """
    online = request.args.get("online", "false").lower() == "true"
    try:
        logger.info(f"Connecting to MySQL at {MYSQL_DATABASE} as {MYSQL_USER}")
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        if online:
            cursor.execute(
                """
                SELECT u.id, u.username, u.email, u.about_me, s.state, ut.type, u.last_online
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                JOIN environment e ON u.environment_id = e.id
                WHERE s.state = 'online' AND u.username NOT IN ('unknown', 'alfr3d') AND e.name = %s
            """,
                (ALFR3D_ENV_NAME,),
            )
        else:
            cursor.execute(
                """
                SELECT u.id, u.username, u.email, u.about_me, s.state, ut.type, u.last_online
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                JOIN environment e ON u.environment_id = e.id
                WHERE u.username NOT IN ('unknown', 'alfr3d') AND e.name = %s
            """,
                (ALFR3D_ENV_NAME,),
            )
        users = []
        for row in cursor.fetchall():
            logger.debug(f"Processing user: {row[1]}")
            users.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "about_me": row[3],
                    "state": row[4],
                    "type": row[5],
                    "last_online": str(row[6]),
                }
            )
        db.close()
        logger.info(f"Returning {len(users)} users")
        return jsonify(users)
    except pymysql.Error as e:
        logger.error(f"Error fetching users: {str(e)}")
        # Return mock data for development
        mock_users = (
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
            ]
            if online
            else [
                {
                    "id": 1,
                    "name": "Alice",
                    "type": "resident",
                    "email": "",
                    "about_me": "",
                    "state": "online",
                    "last_online": "",
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "type": "guest",
                    "email": "",
                    "about_me": "",
                    "state": "offline",
                    "last_online": "",
                },
            ]
        )
        logger.warning("Returning mock user data due to database error")
        return jsonify(mock_users)


@app.route("/api/users", methods=["POST"])
def create_user():
    """
    Create a new user.

    Request Body (JSON):
        name (str): Username (required).
        type (str): User type (required).
        email (str): Email address (optional).
        about_me (str): About me text (optional).

    Returns:
        JSON: Created user info with id, name, type.
    """
    data = request.get_json()
    if not data or "name" not in data or "type" not in data:
        return jsonify({"error": "Missing name or type"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        # Get state id for offline
        cursor.execute("SELECT id FROM states WHERE state = 'offline'")
        state_row = cursor.fetchone()
        if not state_row:
            return jsonify({"error": "Offline state not found"}), 500
        state_id = state_row[0]
        # Get type id
        cursor.execute("SELECT id FROM user_types WHERE type = %s", (data["type"],))
        type_row = cursor.fetchone()
        if not type_row:
            return jsonify({"error": "Invalid user type"}), 400
        type_id = type_row[0]
        # Get env id
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            return jsonify({"error": "Environment not found"}), 500
        env_id = env_row[0]
        cursor.execute(
            "INSERT INTO user (username, email, about_me, state, type, environment_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                data["name"],
                data.get("email", ""),
                data.get("about_me", ""),
                state_id,
                type_id,
                env_id,
            ),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return jsonify({"id": new_id, "name": data["name"], "type": data["type"]}), 201
    except pymysql.Error as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id: int):
    """
    Update an existing user.

    Args:
        user_id (int): ID of the user to update.

    Request Body (JSON):
        name (str): New username (optional).
        email (str): New email (optional).
        about_me (str): New about me text (optional).
        type (str): New user type (optional).

    Returns:
        JSON: Success message.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        updates = []
        params = []
        if "name" in data:
            updates.append("username = %s")
            params.append(data["name"])
        if "email" in data:
            updates.append("email = %s")
            params.append(data["email"])
        if "about_me" in data:
            updates.append("about_me = %s")
            params.append(data["about_me"])
        if "type" in data:
            cursor.execute("SELECT id FROM user_types WHERE type = %s", (data["type"],))
            type_id = cursor.fetchone()
            if type_id:
                updates.append("type = %s")
                params.append(type_id[0])
        if updates:
            params.append(user_id)
            cursor.execute(
                f"UPDATE user SET {', '.join(updates)} WHERE id = %s", params
            )
            db.commit()
        db.close()
        return jsonify({"message": "User updated"})
    except pymysql.Error as e:
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    """
    Delete a user by ID.

    Args:
        user_id (int): ID of the user to delete.

    Returns:
        JSON: Success message.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
        db.commit()
        db.close()
        return jsonify({"message": "User deleted"})
    except pymysql.Error as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": str(e)}), 500


def run_docker_command(command: List[str], env: Dict[str, str]) -> str:
    """Run a Docker command via subprocess and return stdout."""
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=10, env=env
    )
    if result.returncode != 0:
        logger.error(f"Docker command failed: {result.stderr}")
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    return result.stdout


def parse_docker_json(output: str) -> List[Dict[str, Any]]:
    """Parse JSON lines from Docker output into a list of dicts."""
    containers = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:

                containers.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Error parsing JSON: {e}")
    return containers


@app.route("/api/containers")
def get_containers():
    """
    Retrieve list of Docker containers with stats.

    Returns:
        JSON: List of container dictionaries with name, cpu, mem, disk, errors.
    """
    if not docker_available:
        logger.warning("Docker not available, returning mock containers list")
        # Return mock data that represents actual services
        import random

        # Generate somewhat realistic data
        containers = [
            {
                "name": "alfr3d-service-user-1",
                "cpu": round(random.uniform(5, 20), 1),
                "mem": round(random.uniform(30, 60), 1),
                "disk": 20.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-device-1",
                "cpu": round(random.uniform(3, 15), 1),
                "mem": round(random.uniform(25, 45), 1),
                "disk": 15.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-environment-1",
                "cpu": round(random.uniform(8, 25), 1),
                "mem": round(random.uniform(35, 55), 1),
                "disk": 18.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-daemon-1",
                "cpu": round(random.uniform(2, 10), 1),
                "mem": round(random.uniform(20, 35), 1),
                "disk": 12.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-api-1",
                "cpu": round(random.uniform(1, 8), 1),
                "mem": round(random.uniform(15, 30), 1),
                "disk": 8.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-service-frontend-1",
                "cpu": round(random.uniform(5, 15), 1),
                "mem": round(random.uniform(40, 70), 1),
                "disk": 25.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-mysql-1",
                "cpu": round(random.uniform(10, 30), 1),
                "mem": round(random.uniform(50, 80), 1),
                "disk": 30.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-zookeeper-1",
                "cpu": round(random.uniform(2, 8), 1),
                "mem": round(random.uniform(20, 40), 1),
                "disk": 10.0,
                "errors": 0,
            },
            {
                "name": "alfr3d-kafka-1",
                "cpu": round(random.uniform(15, 35), 1),
                "mem": round(random.uniform(60, 90), 1),
                "disk": 40.0,
                "errors": 0,
            },
        ]
        return jsonify(containers)

    try:
        # Set environment for docker commands
        env = os.environ.copy()
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"

        containers = []

        # Get container list
        output = run_docker_command(["docker", "ps", "-a", "--format", "json"], env)
        container_list = parse_docker_json(output)

        for container in container_list:
            container_name = container.get("Names", "").split(",")[0]

            # Filter to only alfr3d containers
            if not container_name.startswith("alfr3d"):
                continue

            logger.debug(
                f"Processing container: {container_name}, status: {container.get('Status', '')}"
            )

            # Get CPU and memory stats
            cpu_percent = 0.0
            mem_percent = 0.0

            try:

                stats_output = run_docker_command(
                    [
                        "docker",
                        "stats",
                        "--no-stream",
                        "--format",
                        "{{.CPUPerc}},{{.MemPerc}}",
                        container_name,
                    ],
                    env,
                )
                stats_line = stats_output.strip()
                if stats_line:
                    parts = stats_line.split(",")
                    if len(parts) >= 2:
                        try:

                            cpu_str = parts[0].rstrip("%")
                            mem_str = parts[1].rstrip("%")
                            cpu_percent = float(cpu_str) if cpu_str else 0.0
                            mem_percent = float(mem_str) if mem_str else 0.0
                        except (ValueError, IndexError):
                            pass
            except subprocess.CalledProcessError:
                pass  # Stats might fail, continue with defaults

            # Get container size for disk estimate
            disk_percent = 15.0  # Default
            try:

                size_output = run_docker_command(
                    [
                        "docker",
                        "ps",
                        "-a",
                        "--size",
                        "--format",
                        "{{.Size}}",
                        "-f",
                        f"name={container_name}",
                    ],
                    env,
                )
                size_str = size_output.strip()
                if size_str:
                    try:

                        # Parse size like "1.23MB (456MB)"
                        size_part = size_str.split(" ")[0]
                        if size_part.endswith("MB"):
                            size_mb = float(size_part[:-2])
                            disk_percent = min(size_mb / 10, 100)
                        elif size_part.endswith("GB"):
                            size_gb = float(size_part[:-2])
                            disk_percent = min(size_gb * 100, 100)
                    except (ValueError, IndexError):
                        pass
            except subprocess.CalledProcessError:
                pass  # Size might fail, continue with default

            # Check for errors (simplified - check if container is running)
            status = container.get("Status", "").lower()
            errors = 0 if "up" in status else 1

            containers.append(
                {
                    "name": container_name,
                    "cpu": round(cpu_percent, 1),
                    "mem": round(mem_percent, 1),
                    "disk": round(disk_percent, 1),
                    "errors": errors,
                }
            )

        logger.info(f"Returning {len(containers)} containers")
        return jsonify(containers)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error fetching containers: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/events")
def get_events():
    """
    Retrieve recent events from Kafka.

    Returns:
        JSON: List of recent events.
    """
    return jsonify(recent_events)


@app.route("/api/situational-awareness")
def get_sa():
    return jsonify(recent_sa if recent_sa else [])


@app.route("/api/devices")
def get_devices():
    """
    Retrieve list of devices.

    Returns:
        JSON: List of device dictionaries with id, name, ip, mac, state, type, user, last_online.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, u.username, d.last_online, d.position_x, d.position_y
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            """,
            (ALFR3D_ENV_NAME,),
        )
        devices = []
        for row in cursor.fetchall():
            logger.debug(f"Processing device: {row[1]}")
            devices.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "ip": row[2],
                    "mac": row[3],
                    "state": row[4],
                    "type": row[5],
                    "user": row[6],
                    "last_online": str(row[7]),
                    "position": (
                        {"x": row[8], "y": row[9]}
                        if row[8] is not None and row[9] is not None
                        else None
                    ),
                }
            )
        db.close()
        return jsonify(devices)
    except pymysql.Error as e:
        logger.error(f"Error fetching devices: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices", methods=["POST"])
def create_device():
    """
    Create a new device.

    Request Body (JSON):
        name (str): Device name (required).
        type (str): Device type (required).
        ip (str): IP address (optional, default 10.0.0.125).
        mac (str): MAC address (optional, default 00:00:00:00:00:00).
        user (str): Associated username (optional).

    Returns:
        JSON: Created device info with id, name, type.
    """
    data = request.get_json()
    if not data or "name" not in data or "type" not in data:
        return jsonify({"error": "Missing name or type"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        # Get state id for offline
        cursor.execute("SELECT id FROM states WHERE state = 'offline'")
        state_row = cursor.fetchone()
        if not state_row:
            return jsonify({"error": "Offline state not found"}), 500
        state_id = state_row[0]
        # Get type id
        cursor.execute("SELECT id FROM device_types WHERE type = %s", (data["type"],))
        type_row = cursor.fetchone()
        if not type_row:
            return jsonify({"error": "Invalid device type"}), 400
        type_id = type_row[0]
        # Get env id
        cursor.execute("SELECT id FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,))
        env_row = cursor.fetchone()
        if not env_row:
            return jsonify({"error": "Environment not found"}), 500
        env_id = env_row[0]
        # Get user id if provided
        user_id = None
        if "user" in data and data["user"]:
            cursor.execute("SELECT id FROM user WHERE username = %s", (data["user"],))
            user_row = cursor.fetchone()
            if user_row:
                user_id = user_row[0]
        cursor.execute(
            "INSERT INTO device (name, IP, MAC, state, device_type, user_id, environment_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                data["name"],
                data.get("ip", "10.0.0.125"),
                data.get("mac", "00:00:00:00:00:00"),
                state_id,
                type_id,
                user_id,
                env_id,
            ),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return jsonify({"id": new_id, "name": data["name"], "type": data["type"]}), 201
    except pymysql.Error as e:
        logger.error(f"Error creating device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/<int:device_id>", methods=["PUT"])
def update_device(device_id):
    """
    Update an existing device.

    Args:
        device_id (int): ID of the device to update.

    Request Body (JSON):
        name (str): New device name (optional).
        ip (str): New IP address (optional).
        mac (str): New MAC address (optional).
        type (str): New device type (optional).
        user (str): New associated username (optional).

    Returns:
        JSON: Success message.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        updates = []
        params = []
        if "name" in data:
            updates.append("name = %s")
            params.append(data["name"])
        if "ip" in data:
            updates.append("IP = %s")
            params.append(data["ip"])
        if "mac" in data:
            updates.append("MAC = %s")
            params.append(data["mac"])
        if "type" in data:
            cursor.execute(
                "SELECT id FROM device_types WHERE type = %s", (data["type"],)
            )
            type_row = cursor.fetchone()
            if type_row:
                updates.append("device_type = %s")
                params.append(type_row[0])
        if "user" in data:
            if data["user"]:
                cursor.execute(
                    "SELECT id FROM user WHERE username = %s", (data["user"],)
                )
                user_row = cursor.fetchone()
                if user_row:
                    updates.append("user_id = %s")
                    params.append(user_row[0])
            else:
                updates.append("user_id = NULL")
        if "position" in data:
            if data["position"] and "x" in data["position"] and "y" in data["position"]:
                updates.append("position_x = %s")
                params.append(data["position"]["x"])
                updates.append("position_y = %s")
                params.append(data["position"]["y"])
            else:
                updates.append("position_x = NULL")
                updates.append("position_y = NULL")
        if updates:
            params.append(device_id)
            cursor.execute(
                f"UPDATE device SET {', '.join(updates)} WHERE id = %s", params
            )
            db.commit()
        db.close()
        return jsonify({"message": "Device updated"})
    except pymysql.Error as e:
        logger.error(f"Error updating device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
def delete_device(device_id):
    """
    Delete a device by ID.

    Args:
        device_id (int): ID of the device to delete.

    Returns:
        JSON: Success message.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM device WHERE id = %s", (device_id,))
        db.commit()
        db.close()
        return jsonify({"message": "Device deleted"})
    except pymysql.Error as e:
        logger.error(f"Error deleting device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>/devices")
def get_user_devices(user_id):
    """
    Retrieve devices associated with a user.

    Args:
        user_id (int): ID of the user.

    Returns:
        JSON: List of device dictionaries for the user.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, d.last_online
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            WHERE d.user_id = %s
            """,
            (user_id,),
        )
        devices = [
            {
                "id": row[0],
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "last_online": str(row[6]),
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return jsonify(devices)
    except pymysql.Error as e:
        logger.error(f"Error fetching user devices: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/<int:device_id>/history")
def get_device_history(device_id):
    """
    Retrieve history of a device.

    Args:
        device_id (int): ID of the device.

    Returns:
        JSON: List of historical device states.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT
                dh.timestamp, dh.name, dh.IP, dh.MAC,
                s.state, dt.type, u.username, dh.last_online
            FROM device_history dh
            LEFT JOIN states s ON dh.state = s.id
            LEFT JOIN device_types dt ON dh.device_type = dt.id
            LEFT JOIN user u ON dh.user_id = u.id
            WHERE dh.device_id = %s
            ORDER BY dh.timestamp DESC
            """,
            (device_id,),
        )
        history = [
            {
                "timestamp": str(row[0]),
                "name": row[1],
                "ip": row[2],
                "mac": row[3],
                "state": row[4],
                "type": row[5],
                "user": row[6],
                "last_online": str(row[7]),
            }
            for row in cursor.fetchall()
        ]
        db.close()
        return jsonify(history)
    except pymysql.Error as e:
        logger.error(f"Error fetching device history: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips", methods=["GET"])
def get_quips():
    """
    Retrieve list of quips.

    Returns:
        JSON: List of quip dictionaries with id, type, quips.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("SELECT id, type, quips FROM quips")
        quips = [
            {"id": row[0], "type": row[1], "quips": row[2]} for row in cursor.fetchall()
        ]
        db.close()
        return jsonify(quips)
    except pymysql.Error as e:
        logger.error(f"Error fetching quips: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips", methods=["POST"])
def create_quip():
    """
    Create a new quip.

    Request Body (JSON):
        type (str): Quip type (required).
        quips (str): Quip text (required).

    Returns:
        JSON: Created quip info with id, type, quips.
    """
    data = request.get_json()
    if not data or "type" not in data or "quips" not in data:
        return jsonify({"error": "Missing type or quips"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO quips (type, quips) VALUES (%s, %s)",
            (data["type"], data["quips"]),
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return (
            jsonify({"id": new_id, "type": data["type"], "quips": data["quips"]}),
            201,
        )
    except pymysql.Error as e:
        logger.error(f"Error creating quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips/<int:quip_id>", methods=["PUT"])
def update_quip(quip_id):
    """
    Update an existing quip.

    Args:
        quip_id (int): ID of the quip to update.

    Request Body (JSON):
        type (str): New quip type (required).
        quips (str): New quip text (required).

    Returns:
        JSON: Updated quip info.
    """
    data = request.get_json()
    if not data or "type" not in data or "quips" not in data:
        return jsonify({"error": "Missing type or quips"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "UPDATE quips SET type = %s, quips = %s WHERE id = %s",
            (data["type"], data["quips"], quip_id),
        )
        db.commit()
        db.close()
        return jsonify({"id": quip_id, "type": data["type"], "quips": data["quips"]})
    except pymysql.Error as e:
        logger.error(f"Error updating quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips/<int:quip_id>", methods=["DELETE"])
def delete_quip(quip_id):
    """
    Delete a quip by ID.

    Args:
        quip_id (int): ID of the quip to delete.

    Returns:
        JSON: Success message.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM quips WHERE id = %s", (quip_id,))
        db.commit()
        db.close()
        return jsonify({"message": "Quip deleted"})
    except pymysql.Error as e:
        logger.error(f"Error deleting quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/weather")
def get_weather():
    """
    Retrieve weather information for the environment.

    Returns:
        JSON: Weather data including city, state, country, low, high, description, sunrise, sunset, humidity.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, description, sunrise, sunset, pressure, humidity, manual_override, manual_location_override FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            weather = {
                "city": row[4],
                "state": row[5],
                "country": row[6],
                "low": row[8],
                "high": row[9],
                "description": row[10],
                "sunrise": str(row[11]) if row[11] else None,
                "sunset": str(row[12]) if row[12] else None,
                "humidity": row[14],
            }
            return jsonify(weather)
        else:
            return jsonify({"error": "Environment not found"}), 404
    except pymysql.Error as e:
        logger.error(f"Error fetching weather: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/environment")
def get_environment():
    """
    Retrieve environment information.

    Returns:
        JSON: Environment data including id, name, location, weather details, overrides.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, latitude, longitude, city, state, country, IP, low, high, description, sunrise, sunset, pressure, humidity, manual_override, manual_location_override FROM environment WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        row = cursor.fetchone()
        db.close()
        logger.debug(f"weather row = {row}")
        if row:
            return jsonify(
                {
                    "id": row[0],
                    "name": row[1],
                    "latitude": row[2],
                    "longitude": row[3],
                    "city": row[4],
                    "state": row[5],
                    "country": row[6],
                    "ip": row[7],
                    "temp_min": row[8],
                    "temp_max": row[9],
                    "description": row[10],
                    "sunrise": str(row[11]) if row[11] else None,
                    "sunset": str(row[12]) if row[12] else None,
                    "pressure": row[13],
                    "humidity": row[14],
                    "manual_override": row[15],
                    "manual_location_override": row[16],
                }
            )
        else:
            return jsonify({"error": "Environment not found"}), 404
    except pymysql.Error as e:
        logger.error(f"Error fetching environment: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/environment", methods=["PUT"])
def update_environment():
    """
    Update environment settings.

    Request Body (JSON):
        latitude (float): Latitude (optional).
        longitude (float): Longitude (optional).
        city (str): City (optional).
        state (str): State (optional).
        country (str): Country (optional).
        IP (str): IP address (optional).
        temp_min (float): Min temperature (optional).
        temp_max (float): Max temperature (optional).
        description (str): Weather description (optional).
        pressure (float): Pressure (optional).
        humidity (float): Humidity (optional).

    Returns:
        JSON: Success message with manual_location_override status.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        updates = []
        params = []
        field_mappings = {
            "latitude": "latitude",
            "longitude": "longitude",
            "city": "city",
            "state": "state",
            "country": "country",
            "IP": "IP",
            "temp_min": "low",
            "temp_max": "high",
            "description": "description",
            "pressure": "pressure",
            "humidity": "humidity",
        }
        location_fields = ["latitude", "longitude", "city", "state", "country", "IP"]
        manual_location_override = (
            1 if any(field in data for field in location_fields) else 0
        )
        for field, db_field in field_mappings.items():
            if field in data:
                updates.append(f"{db_field} = %s")
                params.append(data[field])
        updates.append("manual_location_override = %s")
        params.append(manual_location_override)
        if updates:
            params.append(ALFR3D_ENV_NAME)
            sql = f"UPDATE environment SET {', '.join(updates)} WHERE name = %s"
            cursor.execute(sql, params)
            db.commit()
        db.close()
        return jsonify(
            {
                "message": "Environment updated",
                "manual_location_override": manual_location_override,
            }
        )
    except pymysql.Error as e:
        logger.error(f"Error updating environment: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/environment/reset", methods=["POST"])
def reset_environment():
    """
    Reset environment to auto-detect location.

    Returns:
        JSON: Success message.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "UPDATE environment SET manual_location_override = 0 WHERE name = %s",
            (ALFR3D_ENV_NAME,),
        )
        db.commit()
        db.close()
        return jsonify({"message": "Environment reset to auto-detect"})
    except pymysql.Error as e:
        logger.error(f"Error resetting environment: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Start event consumer threads
    threading.Thread(target=consume_events, daemon=True).start()
    threading.Thread(target=consume_sa, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)
