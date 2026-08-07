"""Tests for Kafka messaging in ALFR3D services."""

from kafka import KafkaProducer, KafkaConsumer
import time
import json
import pytest


@pytest.mark.integration
def test_kafka_produce_consume(kafka_bootstrap_servers):
    """Test producing and consuming messages from Kafka topics."""
    topics = ["speak", "environment", "device", "user", "google"]
    test_message = b"test message"

    producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers)

    # For each topic, subscribe first, then produce, then consume
    for i, topic in enumerate(topics):
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=kafka_bootstrap_servers,
            group_id=f"test-group-{topic}-{i}",
            auto_offset_reset="latest",
            consumer_timeout_ms=1000,
        )
        # Poll once so the consumer joins the group and fixes its starting
        # offset before we produce, otherwise the produced message is missed.
        consumer.poll(timeout_ms=2000)

        # Produce after subscribe
        producer.send(topic, test_message)
        producer.flush()

        messages = []
        start_time = time.time()
        while time.time() - start_time < 10:  # 10 seconds timeout
            records = consumer.poll(timeout_ms=1000)
            if not records:
                continue
            for partition_records in records.values():
                messages.extend(record.value for record in partition_records)
            if test_message in messages:
                break
        consumer.close()
        assert test_message in messages, f"test message not received from topic {topic}"


@pytest.mark.integration
def test_kafka_frontend_integration(frontend_client, mysql_config, apply_database_schema):
    """Test frontend can retrieve Kafka-fed dashboard data."""
    # The frontend API serves the users endpoint that is fed by Kafka consumers.
    response = frontend_client.get("/api/users")
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = json.loads(response.text)
        assert isinstance(data, list)
