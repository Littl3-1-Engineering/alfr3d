import time
import threading
import logging
from typing import Any, Callable, Optional

from .redis_client import (
    redis_get,
    redis_set,
    redis_delete,
    redis_delete_pattern,
    is_redis_available,
)

logger = logging.getLogger("ApiLog")


class TTLCache:
    """Cache with Redis backend and in-memory fallback."""

    def __init__(self, default_ttl: int = 300):
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        # In-memory fallback
        self._cache = {}
        self._timestamps = {}

    def get(self, key: str) -> Optional[Any]:
        # Try Redis first
        if is_redis_available():
            val = redis_get(key)
            if val is not None:
                return val

        # Fallback to in-memory
        with self._lock:
            if key not in self._cache:
                return None
            if self._is_expired(key):
                del self._cache[key]
                del self._timestamps[key]
                return None
            return self._cache[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl

        # Try Redis first
        if is_redis_available():
            redis_set(key, value, effective_ttl)

        # Also store in-memory as fallback
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time() + effective_ttl

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        val = self.get(key)
        if val is not None:
            return val
        result = factory()
        self.set(key, result, ttl)
        return result

    def invalidate(self, key: str) -> None:
        if is_redis_available():
            redis_delete(key)
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern. Returns count deleted."""
        count = 0
        if is_redis_available():
            count = redis_delete_pattern(pattern)
        with self._lock:
            matching = [k for k in self._cache if k.startswith(pattern.replace("*", ""))]
            for k in matching:
                del self._cache[k]
                self._timestamps.pop(k, None)
                count += 1
        return count

    def clear(self) -> None:
        if is_redis_available():
            redis_delete_pattern("*")
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def _is_expired(self, key: str) -> bool:
        if key not in self._timestamps:
            return True
        return time.time() > self._timestamps[key]


_api_cache = TTLCache(default_ttl=300)


def get_cache() -> TTLCache:
    return _api_cache


def cached_endpoint(ttl: int = 300):
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            cache = get_cache()
            cache_key = f"{func.__module__}.{func.__name__}"
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
