"""Tests for the ALFR3D device service."""

from confluent_kafka import Producer


def test_device_service_scan_net(kafka_bootstrap_servers):
    """Test sending 'scan net' message to device topic and verify response."""
    from conftest import wait_for_kafka_message

    # Send scan net message
    producer = Producer({"bootstrap.servers": kafka_bootstrap_servers})
    producer.produce("device", value=b"scan net")
    producer.flush()

    # Wait for response on user topic
    found = wait_for_kafka_message(kafka_bootstrap_servers, "user", "refresh-all", timeout=15)
    assert found, "refresh-all not sent to user topic"


def test_device_service_health_check(frontend_client):
    """Test device service health endpoint via frontend."""
    # This tests that the frontend can reach the device service health endpoint
    # In a real scenario, this would test the actual health check functionality
    response = frontend_client.get("/dashboard/data")

    # Just verify the endpoint returns data (even if mocked)
    assert response.status_code == 200
    import json

    data = json.loads(response.data)
    assert "device" in data
    assert "status" in data["device"]
