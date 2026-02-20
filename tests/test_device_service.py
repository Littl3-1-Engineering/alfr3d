"""Tests for the ALFR3D device service."""

import json
import time
from confluent_kafka import Consumer, Producer


def wait_for_kafka_message(kafka_bootstrap_servers, topic, expected_value, timeout=30):
    """Helper function to wait for a Kafka message containing expected_value."""
    import uuid

    consumer = Consumer(
        {
            "bootstrap.servers": kafka_bootstrap_servers,
            "group.id": f"test-group-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    start_time = time.time()
    while time.time() - start_time < timeout:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            continue
        message_value = msg.value().decode("utf-8")
        if expected_value in message_value:
            consumer.close()
            return True
    consumer.close()
    return False


def test_device_service_scan_net(kafka_bootstrap_servers):
    """Test sending 'scan net' message to device topic and verify response."""

    # Send scan net message
    producer = Producer({"bootstrap.servers": kafka_bootstrap_servers})
    producer.produce("device", value=b"scan net")
    producer.flush()

    # Wait for response on user topic
    found = wait_for_kafka_message(kafka_bootstrap_servers, "user", "refresh-all", timeout=15)
    assert found, "refresh-all not sent to user topic"


def test_device_service_health_check(frontend_client):
    """Test frontend users endpoint."""
    response = frontend_client.get("/api/users")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
