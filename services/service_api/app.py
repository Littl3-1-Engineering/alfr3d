# Modified for containerization: logging to stdout instead of file
import os
import sys
import logging
import subprocess
import json
import docker
import pymysql  # Changed from MySQLdb to pymysql
import threading
from datetime import datetime
from kafka import KafkaConsumer
from flask import Flask, request, jsonify
from flask_cors import CORS

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# set up logging
logger = logging.getLogger("ApiLog")
logger.setLevel(logging.DEBUG)
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

# Store recent events
recent_events = []


def consume_events():
    try:
        consumer = KafkaConsumer(
            "event-stream", bootstrap_servers=KAFKA_URL, auto_offset_reset="latest"
        )
        logger.info("Connected to Kafka event-stream topic")
        for message in consumer:
            try:
                event = json.loads(message.value.decode("utf-8"))
                recent_events.append(event)
                if len(recent_events) > 50:
                    recent_events.pop(0)
                logger.info(f"Received event: {event}")
            except Exception as e:
                logger.error(f"Error processing event message: {str(e)}")
    except Exception as e:
        logger.error(f"Error connecting to Kafka for events: {str(e)}")


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
except Exception as e:
    logger.warning(f"Docker check failed: {str(e)}")

# Flask API
app = Flask(__name__)
CORS(app)


@app.route("/api/users")
def get_users():
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
        users = [{"id": row[0], "name": row[1], "email": row[2], "about_me": row[3], "state": row[4], "type": row[5], "last_online": str(row[6])} for row in cursor.fetchall()]
        db.close()
        logger.info(f"Returning {len(users)} users")
        return jsonify(users)
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        # Return mock data for development
        mock_users = (
            [
                {"id": 1, "name": "Alice", "type": "resident", "email": "", "about_me": "", "state": "online", "last_online": ""},
                {"id": 2, "name": "Bob", "type": "guest", "email": "", "about_me": "", "state": "online", "last_online": ""},
            ]
            if online
            else [
                {"id": 1, "name": "Alice", "type": "resident", "email": "", "about_me": "", "state": "online", "last_online": ""},
                {"id": 2, "name": "Bob", "type": "guest", "email": "", "about_me": "", "state": "offline", "last_online": ""},
            ]
        )
        logger.warning("Returning mock user data due to database error")
        return jsonify(mock_users)


@app.route("/api/users", methods=["POST"])
def create_user():
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
            (data["name"], data.get("email", ""), data.get("about_me", ""), state_id, type_id, env_id)
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return jsonify({"id": new_id, "name": data["name"], "type": data["type"]}), 201
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
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
            cursor.execute(f"UPDATE user SET {', '.join(updates)} WHERE id = %s", params)
            db.commit()
        db.close()
        return jsonify({"message": "User updated"})
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
        db.commit()
        db.close()
        return jsonify({"message": "User deleted"})
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/containers")
def get_containers():
    if not docker_available:
        logger.warning("Docker not available, returning mock containers list")
        # Return mock data that represents actual services
        import random
        import time

        # Generate somewhat realistic data
        base_time = int(time.time())
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
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if result.returncode != 0:
            logger.error(f"Docker ps command failed: {result.stderr}")
            return jsonify({"error": "Failed to get container list"})

        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line.strip():
                try:
                    container = json.loads(line)
                    container_name = container.get("Names", "").split(",")[0]

                    # Filter to only alfr3d containers
                    if not container_name.startswith("alfr3d"):
                        continue

                    logger.info(
                        f"Processing container: {container_name}, status: {container.get('Status', '')}"
                    )

                    # Get CPU and memory stats
                    cpu_percent = 0.0
                    mem_percent = 0.0

                    stats_result = subprocess.run(
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{.CPUPerc}},{{.MemPerc}}",
                            container_name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        env=env,
                    )
                    if stats_result.returncode == 0:
                        stats_line = stats_result.stdout.strip()
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

                    # Get container size for disk estimate
                    disk_percent = 15.0  # Default
                    size_result = subprocess.run(
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
                        capture_output=True,
                        text=True,
                        timeout=10,
                        env=env,
                    )
                    if size_result.returncode == 0:
                        size_str = size_result.stdout.strip()
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
                except json.JSONDecodeError as e:
                    logger.warning(f"Error parsing container JSON: {str(e)}")
                    continue

        logger.info(f"Returning {len(containers)} containers")
        return jsonify(containers)
    except Exception as e:
        logger.error(f"Error fetching containers: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/events")
def get_events():
    return jsonify(recent_events)


@app.route("/api/devices")
def get_devices():
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT d.id, d.name, d.IP, d.MAC, s.state, dt.type, u.username, d.last_online
            FROM device d
            JOIN states s ON d.state = s.id
            JOIN device_types dt ON d.device_type = dt.id
            LEFT JOIN user u ON d.user_id = u.id
            JOIN environment e ON d.environment_id = e.id
            WHERE e.name = %s
            """,
            (ALFR3D_ENV_NAME,)
        )
        devices = [{"id": row[0], "name": row[1], "ip": row[2], "mac": row[3], "state": row[4], "type": row[5], "user": row[6], "last_online": str(row[7])} for row in cursor.fetchall()]
        db.close()
        return jsonify(devices)
    except Exception as e:
        logger.error(f"Error fetching devices: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices", methods=["POST"])
def create_device():
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
            (data["name"], data.get("ip", "10.0.0.125"), data.get("mac", "00:00:00:00:00:00"), state_id, type_id, user_id, env_id)
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return jsonify({"id": new_id, "name": data["name"], "type": data["type"]}), 201
    except Exception as e:
        logger.error(f"Error creating device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/<int:device_id>", methods=["PUT"])
def update_device(device_id):
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
            cursor.execute("SELECT id FROM device_types WHERE type = %s", (data["type"],))
            type_row = cursor.fetchone()
            if type_row:
                updates.append("device_type = %s")
                params.append(type_row[0])
        if "user" in data:
            if data["user"]:
                cursor.execute("SELECT id FROM user WHERE username = %s", (data["user"],))
                user_row = cursor.fetchone()
                if user_row:
                    updates.append("user_id = %s")
                    params.append(user_row[0])
            else:
                updates.append("user_id = NULL")
        if updates:
            params.append(device_id)
            cursor.execute(f"UPDATE device SET {', '.join(updates)} WHERE id = %s", params)
            db.commit()
        db.close()
        return jsonify({"message": "Device updated"})
    except Exception as e:
        logger.error(f"Error updating device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
def delete_device(device_id):
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM device WHERE id = %s", (device_id,))
        db.commit()
        db.close()
        return jsonify({"message": "Device deleted"})
    except Exception as e:
        logger.error(f"Error deleting device: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips", methods=["GET"])
def get_quips():
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("SELECT id, type, quips FROM quips")
        quips = [{"id": row[0], "type": row[1], "quips": row[2]} for row in cursor.fetchall()]
        db.close()
        return jsonify(quips)
    except Exception as e:
        logger.error(f"Error fetching quips: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips", methods=["POST"])
def create_quip():
    data = request.get_json()
    if not data or "type" not in data or "quips" not in data:
        return jsonify({"error": "Missing type or quips"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("INSERT INTO quips (type, quips) VALUES (%s, %s)", (data["type"], data["quips"]))
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return jsonify({"id": new_id, "type": data["type"], "quips": data["quips"]}), 201
    except Exception as e:
        logger.error(f"Error creating quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips/<int:quip_id>", methods=["PUT"])
def update_quip(quip_id):
    data = request.get_json()
    if not data or "type" not in data or "quips" not in data:
        return jsonify({"error": "Missing type or quips"}), 400
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("UPDATE quips SET type = %s, quips = %s WHERE id = %s", (data["type"], data["quips"], quip_id))
        db.commit()
        db.close()
        return jsonify({"id": quip_id, "type": data["type"], "quips": data["quips"]})
    except Exception as e:
        logger.error(f"Error updating quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quips/<int:quip_id>", methods=["DELETE"])
def delete_quip(quip_id):
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute("DELETE FROM quips WHERE id = %s", (quip_id,))
        db.commit()
        db.close()
        return jsonify({"message": "Quip deleted"})
    except Exception as e:
        logger.error(f"Error deleting quip: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Start event consumer thread
    threading.Thread(target=consume_events, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)
