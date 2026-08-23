"""Fixed-window rate limiting for auth endpoints, backed by Redis.

Fails open if Redis is unavailable -- matches every existing redis_client.py caller's fail-soft
behavior. Deliberate tradeoff: this is a self-hosted household app, not a public multi-tenant
target, so "briefly unthrottled if the cache is down" is acceptable; silently locking every login
out because Redis hiccupped would be worse.
"""

from common import redis_incr_with_ttl


def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Returns True if the caller is still within budget (and records this attempt), False if
    they've exceeded max_attempts within the current window."""
    count = redis_incr_with_ttl(key, window_seconds)
    if count is None:
        return True
    return count <= max_attempts
