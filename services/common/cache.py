import time
import threading
from typing import Any, Callable, Optional


class TTLCache:
    def __init__(self, default_ttl: int = 300):
        self._cache = {}
        self._timestamps = {}
        self._default_ttl = default_ttl
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None

            if self._is_expired(key):
                del self._cache[key]
                del self._timestamps[key]
                return None

            return self._cache[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time() + (ttl if ttl is not None else self._default_ttl)

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        with self._lock:
            value = self.get(key)
            if value is not None:
                return value

            value = factory()
            self.set(key, value, ttl)
            return value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self) -> None:
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
