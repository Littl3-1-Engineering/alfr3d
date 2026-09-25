"""Tests for the shared Redis cache wrapper."""

import decimal
from unittest.mock import MagicMock, patch

import orjson

from common.redis_client import _json_default, redis_set


@patch("common.redis_client.get_redis")
def test_redis_set_serializes_a_decimal_bearing_payload(mock_get_redis):
    """MySQL hands back DECIMAL columns as decimal.Decimal; orjson has no native encoder for
    one, so this used to raise, log at WARNING and return False -- silently leaving the payload
    out of the shared cache. `environment.latitude/longitude` are decimal(20,10), which made
    `api:environment` the live victim."""
    redis = MagicMock()
    mock_get_redis.return_value = redis

    payload = {"latitude": decimal.Decimal("43.6439720000"), "city": "Toronto"}
    assert redis_set("api:environment", payload, 300) is True

    _key, _ttl, blob = redis.setex.call_args[0]
    assert orjson.loads(blob) == {"latitude": 43.643972, "city": "Toronto"}


@patch("common.redis_client.get_redis")
def test_redis_set_returns_false_for_a_genuinely_unserializable_payload(mock_get_redis):
    """The Decimal handler is a safety net, not a blanket `str()` fallback -- anything else
    still fails rather than silently caching a mangled value."""
    redis = MagicMock()
    mock_get_redis.return_value = redis

    assert redis_set("api:whatever", {"x": object()}, 300) is False
    redis.setex.assert_not_called()


@patch("common.redis_client.get_redis")
def test_redis_set_logs_a_serialization_failure_at_error(mock_get_redis, caplog):
    """A payload this function cannot encode is a code defect and will fail identically on every
    retry, so it is logged louder than a connection blip. The Decimal bug sat unnoticed for
    exactly this reason."""
    mock_get_redis.return_value = MagicMock()

    with caplog.at_level("WARNING", logger="ApiLog"):
        redis_set("api:whatever", {"x": object()}, 300)

    assert [r.levelname for r in caplog.records] == ["ERROR"]


@patch("common.redis_client.get_redis")
def test_redis_set_still_logs_a_connection_failure_at_warning(mock_get_redis, caplog):
    redis = MagicMock()
    redis.setex.side_effect = ConnectionError("connection refused")
    mock_get_redis.return_value = redis

    with caplog.at_level("WARNING", logger="ApiLog"):
        assert redis_set("api:environment", {"city": "Toronto"}, 300) is False

    assert [r.levelname for r in caplog.records] == ["WARNING"]


def test_json_default_converts_decimal_and_rejects_everything_else():
    assert _json_default(decimal.Decimal("1.5")) == 1.5

    try:
        _json_default(object())
    except TypeError as e:
        assert "not JSON serializable" in str(e)
    else:
        raise AssertionError("expected a TypeError for an unhandled type")
