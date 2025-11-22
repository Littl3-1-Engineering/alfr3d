"""Pytest configuration and fixtures for ALFR3D services testing."""
import os
import time
import pytest
import pymysql
from confluent_kafka import Consumer
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def is_mysql_responsive(host, port):
    try:
        conn = pymysql.connect(host=host, port=port, user="root", password="testrootpassword", database="test_alfr3d_db")
        conn.close()
        return True
    except Exception:
        return False

def wait_for_kafka_message(kafka_bootstrap_servers, topic, expected_value, timeout=30):
    """Helper function to wait for a Kafka message containing expected_value."""
    import uuid
    consumer = Consumer({
        'bootstrap.servers': kafka_bootstrap_servers,
        'group.id': f'test-group-{uuid.uuid4()}',
        'auto.offset.reset': 'earliest'
    })
    consumer.subscribe([topic])
    start_time = time.time()
    while time.time() - start_time < timeout:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            continue
        message_value = msg.value().decode('utf-8')
        if expected_value in message_value:
            consumer.close()
            return True
    consumer.close()
    return False

def wait_for_db_user(mysql_config, username, exists=True, timeout=30):
    """Helper function to wait for a user to exist or not exist in DB."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        conn = pymysql.connect(**mysql_config)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if exists and user is not None:
            return True
        if not exists and user is None:
            return True
        time.sleep(0.5)
    return False

@pytest.fixture(scope="session")
def kafka_bootstrap_servers():
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

@pytest.fixture(scope="session")
def mysql_service(docker_ip, docker_services):
    """Fixture to ensure the MySQL container is fully responsive before any tests run."""
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_mysql_responsive(docker_ip, 3307)
    )

@pytest.fixture(scope="session")
def mysql_config(mysql_service, docker_ip):
    return {
        "host": docker_ip,
        "port": 3307,
        "user": "root",
        "password": "testrootpassword",
        "database": "test_alfr3d_db",
    }

@pytest.fixture(scope="session")
def frontend_app():
    """Flask app fixture for frontend tests."""
    from services.service_frontend.app import app
    app.config['TESTING'] = True
    return app

@pytest.fixture(scope="session")
def frontend_client(frontend_app):
    """Flask test client for frontend tests."""
    return frontend_app.test_client()

@pytest.fixture(scope="session")
def apply_database_schema(mysql_config):
    """Apply database schema and seed data for tests."""
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    
    # Read and execute schema SQL
    with open("setup/createTables.sql", "r") as f:
        sql = f.read()
    # Split by semicolon and execute each statement
    statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
    for stmt in statements:
        if stmt:
            cursor.execute(stmt)
    
    conn.commit()
    cursor.close()
    conn.close()