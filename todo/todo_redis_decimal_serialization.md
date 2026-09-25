# Redis cache: `decimal.Decimal` breaks JSON serialization

## Status: 🟡 Built 2026-09-23 — all three design items shipped with tests; not yet deployed
to the NUC, so the live check below is still owed

Found incidentally while fixing the Kafka container-health misreport (`/api/containers`
reporting a healthy Kafka at 0%, 2026-09-22); unrelated to that work and deliberately left
unfixed there to keep that change focused.

**What shipped 2026-09-23:**

- **§1** — `_fetch_environment()` (`services/service_api/dependencies.py:356`) casts `latitude` /
  `longitude` with `float(row[n]) if row[n] is not None else None`. The None guard matters: both
  columns are nullable and `fetch_home_coordinates()` relies on None meaning "no coordinates
  set", so a bare `float()` would have turned a missing-coordinates household into a crash.
- **§2** — `redis_set()` passes a new `_json_default` handler (`redis_client.py:69`) that
  converts `Decimal` → `float` and re-raises `TypeError` for anything else, so the net stays a
  net rather than becoming a blanket `str()` fallback.
- **§3** — a serialization failure now logs at **ERROR** (`Redis SET serialization error for
  …`) while a connection failure stays at WARNING. `orjson.JSONEncodeError` subclasses
  `TypeError` — verified in this environment rather than assumed — so `except TypeError` catches
  the encode path cleanly ahead of the general handler.
- **Tests** — new `tests/test_redis_client.py` (5: Decimal round-trip, non-Decimal still refused,
  ERROR vs WARNING levels, `_json_default` directly) plus 2 in `tests/test_api_service.py`
  covering `_fetch_environment`'s float cast and its None passthrough. Full suite 625 passed;
  flake8 + black clean on all four touched files.

**Still owed:** the live check under Testing below — deploy, hit `/api/environment`, confirm an
`api:environment` key appears in `redis-cli --scan`, and confirm no `Redis SET error` warning is
logged.

## Overview

_Describes the bug as found on 2026-09-22 — present tense throughout this section and the
Design section below refers to the pre-fix code. See the status block above for what changed._

`redis_set()` (`services/common/redis_client.py:82`) serializes with a bare
`orjson.dumps(value)`. orjson has no native encoder for `decimal.Decimal` and no `default=`
handler is passed, so it raises `TypeError` for any payload containing one. The exception is
caught and logged at WARNING, and the function returns `False` — **the caller never finds out**:

```
ApiLog - WARNING - Redis SET error for api:environment: Type is not JSON serializable: decimal.Decimal
```

MySQL returns `DECIMAL` columns as `decimal.Decimal`, and `environment.latitude` /
`environment.longitude` are `decimal(20,10)`, so `_fetch_environment()`
(`services/service_api/dependencies.py:356`) always produces a Decimal-bearing dict.

### Live reproduction (prod NUC, 2026-09-22)

Hitting both cached endpoints and then listing Redis keys:

```
$ redis-cli --scan
weather_forecast:43.6439720000:-79.5889170000:6
api:weather                 <- written fine, no Decimal in the payload
                            <- api:environment absent
$ docker logs --since 2m alfr3d-service-api-1 | grep "Redis SET error"
... Redis SET error for api:environment: Type is not JSON serializable: decimal.Decimal
```

`api:weather` proves the cache path itself is healthy; only the Decimal-bearing payload fails.

## Impact — degraded, not absent

`TTLCache.set()` (`services/common/cache.py:44`) writes to Redis **and** to a per-process
in-memory dict, and the in-memory write succeeds. So `api:environment` is still cached for its
300s TTL inside a single API process. What is actually lost:

- **No cross-process sharing.** Each process keeps its own copy; the shared cache is the whole
  point of backing `TTLCache` with Redis.
- **No survival across restarts.** An API restart drops the cache entirely.
- **Invalidation can go stale.** `_invalidate_cache("api:environment")`
  (`routes/environment.py:93`, `routes/integrations.py:44`) deletes the Redis key and the
  *calling* process's in-memory entry. Another process's in-memory copy is untouched and can
  serve stale environment data for up to 300s after a manual override or an integrations sync.
- **Recurring WARNING noise** every time the in-memory entry expires and the write is retried.

## Design

Two changes, both wanted — fixing only one leaves a sharp edge.

### 1. Normalize at the source (`_fetch_environment`)

Cast `latitude` / `longitude` to `float` when building the dict. This is observably a no-op on
the wire: FastAPI's `jsonable_encoder` already converts Decimal to a JSON number, and
`GET /api/environment` returns `43.643972` as a float today.

### 2. Give `redis_set()` a `default=` handler

```python
def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError

r.setex(key, ttl, orjson.dumps(value, default=_json_default))
```

A safety net so a future Decimal-bearing payload degrades to a float instead of silently
killing the cache write.

**Why both:** with only #2, a Redis *hit* returns `float` (JSON round-trip) while a *miss*
returns `Decimal` — the same function handing back two different types depending on cache
state, which is a worse bug than the one being fixed. #1 makes both paths agree.

### 3. Consider surfacing the failure

`redis_set()` already returns a bool that every caller discards; `TTLCache.set()` ignores it.
A silent-failure-with-warning is why this sat unnoticed. At minimum, log at ERROR for a
serialization failure (a code defect) versus a connection failure (an operational blip).

## Scope check

`decimal` columns in the prod schema (2026-09-22):

| table | columns |
|---|---|
| `environment` | `latitude`, `longitude` — `decimal(20,10)` |
| `device_location_history` | `latitude`, `longitude` — `decimal(9,6)` |

`device_location_history` is not cached through `TTLCache` today, so `api:environment` is the
only live victim — but it is the same latent trap for any future cached query over either table.

## Testing

- Unit: `redis_set()` with a `Decimal`-bearing dict round-trips instead of returning `False`.
- Unit: `_fetch_environment()` returns `float` for lat/long.
- Live: hit `/api/environment`, confirm an `api:environment` key appears in Redis and no
  `Redis SET error` warning is logged.
