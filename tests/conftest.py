"""Pytest configuration and fixtures for ALFR3D services testing.

Fixtures that need external infrastructure (MySQL, Kafka) are driven by
environment variables and automatically ``pytest.skip`` when the infrastructure
is not reachable, so the unit test suite runs anywhere. Integration tests run
when the infra is available (e.g. in CI, where MySQL and Kafka are started via
GitHub Actions services or the ``tests/docker-compose.yml`` stack).
"""

import os
import time
import pytest
import pymysql
from kafka import KafkaConsumer, KafkaProducer
from dotenv import load_dotenv

load_dotenv()


def is_mysql_responsive(config, timeout=5):
    try:
        conn = pymysql.connect(**config, connect_timeout=timeout)
        conn.close()
        return True
    except Exception:
        return False


def wait_for_kafka_message(kafka_bootstrap_servers, topic, expected_value, timeout=30):
    """Helper function to wait for a Kafka message containing expected_value."""
    import uuid

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap_servers,
        group_id=f"test-group-{uuid.uuid4()}",
        auto_offset_reset="earliest",
        consumer_timeout_ms=1000,
    )
    start_time = time.time()
    while time.time() - start_time < timeout:
        records = consumer.poll(timeout_ms=1000)
        if not records:
            continue
        for partition_records in records.values():
            for record in partition_records:
                message_value = record.value.decode("utf-8")
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


def _mysql_config_from_env():
    return {
        "host": os.getenv("MYSQL_TEST_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_TEST_PORT", "3306")),
        "user": os.getenv("MYSQL_TEST_USER", "root"),
        "password": os.getenv("MYSQL_TEST_PASSWORD", "testrootpassword"),
        "database": os.getenv("MYSQL_TEST_DB", "test_alfr3d_db"),
    }


@pytest.fixture(scope="session")
def kafka_bootstrap_servers():
    """Kafka bootstrap servers for integration tests, skipping if unavailable."""
    servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    try:
        consumer = KafkaConsumer(
            "test-reachability",
            bootstrap_servers=servers,
            auto_offset_reset="earliest",
            consumer_timeout_ms=1000,
        )
        consumer.poll(timeout_ms=3000)
        consumer.close()
    except Exception as exc:
        pytest.skip(f"Kafka unavailable at {servers}: {exc}")
    return servers


@pytest.fixture(scope="session")
def mysql_config():
    """MySQL connection settings for integration tests, skipping if unavailable."""
    config = _mysql_config_from_env()
    if not is_mysql_responsive(config):
        pytest.skip(
            f"MySQL test database unavailable at {config['host']}:{config['port']}"
        )
    return config


@pytest.fixture(scope="session")
def frontend_app():
    """FastAPI app fixture for frontend tests."""
    from services.service_frontend.app import app

    return app


@pytest.fixture(scope="session")
def frontend_client(frontend_app):
    """FastAPI TestClient for frontend tests."""
    from fastapi.testclient import TestClient

    return TestClient(frontend_app)


@pytest.fixture(scope="session")
def apply_database_schema(mysql_config):
    """Apply database schema and seed data for tests."""
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()

    with open("setup/createTables.sql", "r") as f:
        sql = f.read()
    statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
    for stmt in statements:
        if stmt:
            cursor.execute(stmt)

    conn.commit()
    cursor.close()
    conn.close()
    return True
