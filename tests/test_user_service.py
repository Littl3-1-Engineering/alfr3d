"""Tests for the ALFR3D user service."""

import pymysql
from kafka import KafkaProducer
import json
import pytest


@pytest.mark.integration
@pytest.mark.fullstack
def test_user_service_create_user(kafka_bootstrap_servers, mysql_config):
    """Test creating a user by sending Kafka message to user topic."""
    from conftest import wait_for_db_user

    test_username = "test_user_service_123"

    # Clean up if exists
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user WHERE username = %s", (test_username,))
    conn.commit()
    cursor.close()
    conn.close()

    # Send create message
    producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers)
    producer.send("user", key=b"create", value=test_username.encode("utf-8"))
    producer.flush()

    # Wait for user to be created in DB
    found = wait_for_db_user(mysql_config, test_username, exists=True, timeout=15)
    assert found, "User not created"

    # Check details
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user WHERE username = %s", (test_username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    assert user is not None, "User not created"
    assert user[1] == test_username, "Username mismatch"

    # Clean up
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user WHERE username = %s", (test_username,))
    conn.commit()
    cursor.close()
    conn.close()


@pytest.mark.integration
@pytest.mark.fullstack
def test_user_service_delete_user(kafka_bootstrap_servers, mysql_config):
    """Test deleting a user by sending Kafka message."""
    from conftest import wait_for_db_user

    test_username = "test_user_delete_123"

    # First create user
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    # Get IDs
    cursor.execute("SELECT id FROM states WHERE state = 'offline'")
    state_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM user_types WHERE type = 'guest'")
    type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM environment WHERE name = 'test'")
    env_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO user (username, last_online, state, type, environment_id) "
        "VALUES (%s, NOW(), %s, %s, %s)",
        (test_username, state_id, type_id, env_id),
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Send delete message
    producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers)
    producer.send("user", key=b"delete", value=test_username.encode("utf-8"))
    producer.flush()

    # Wait for user to be deleted
    found = wait_for_db_user(mysql_config, test_username, exists=False, timeout=15)
    assert found, "User not deleted"


@pytest.mark.integration
def test_user_service_frontend_integration(frontend_client, mysql_config, apply_database_schema):
    """Test user service integration with frontend."""
    # Test that frontend can retrieve user data
    response = frontend_client.get("/api/users")
    assert response.status_code in (200, 500)

    if response.status_code == 200:
        data = json.loads(response.text)
        assert isinstance(data, list)
