"""Redis client wrapper for ALFR3D caching."""

import os
import logging
import json
from typing import Any, Optional

logger = logging.getLogger("ApiLog")

_redis_client = None
_available = False


def get_redis():
    """Get the Redis client singleton. Returns None if unavailable."""
    global _redis_client, _available

    if _redis_client is not None:
        return _redis_client

    try:
        import redis

        host = os.environ.get("REDIS_HOST", "redis")
        port = int(os.environ.get("REDIS_PORT", 6379))

        _redis_client = redis.Redis(
            host=host,
            port=port,
            db=0,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        _redis_client.ping()
        _available = True
        logger.info(f"Redis connected at {host}:{port}")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable, falling back to in-memory cache: {e}")
        _available = False
        return None


def is_redis_available() -> bool:
    """Check if Redis is available. Triggers connection on first call."""
    if _available:
        return True
    get_redis()
    return _available


def redis_get(key: str) -> Optional[Any]:
    """Get a value from Redis, deserializing JSON."""
    r = get_redis()
    if r is None:
        return None
    try:
        val = r.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.warning(f"Redis GET error for {key}: {e}")
        return None


def redis_set(key: str, value: Any, ttl: int = 300) -> bool:
    """Set a value in Redis with TTL, serializing to JSON."""
    r = get_redis()
    if r is None:
        return False
    try:
        r.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning(f"Redis SET error for {key}: {e}")
        return False


def redis_delete(key: str) -> bool:
    """Delete a key from Redis."""
    r = get_redis()
    if r is None:
        return False
    try:
        r.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis DEL error for {key}: {e}")
        return False


def redis_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns count of deleted keys."""
    r = get_redis()
    if r is None:
        return 0
    try:
        keys = list(r.scan_iter(match=pattern, count=100))
        if keys:
            return r.delete(*keys)
        return 0
    except Exception as e:
        logger.warning(f"Redis DEL pattern error for {pattern}: {e}")
        return 0
