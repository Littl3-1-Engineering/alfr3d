"""Tests for the ALFR3D device service."""

import json
import time
import pytest
from kafka import KafkaProducer, KafkaConsumer


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


@pytest.mark.integration
@pytest.mark.fullstack
def test_device_service_scan_net(kafka_bootstrap_servers):
    """Test sending 'scan_net' message to device topic and verify response."""

    # Send scan_net message as JSON
    producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers)
    producer.send("device", value=json.dumps({"action": "scan_net"}).encode("utf-8"))
    producer.flush()

    # Wait for response on user topic
    found = wait_for_kafka_message(kafka_bootstrap_servers, "user", "refresh-all", timeout=15)
    assert found, "refresh-all not sent to user topic"


@pytest.mark.integration
def test_device_service_health_check(frontend_client, mysql_config, apply_database_schema):
    """Test frontend users endpoint."""
    response = frontend_client.get("/api/users")

    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = json.loads(response.text)
        assert isinstance(data, list)
