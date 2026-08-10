# ALFR3D Codebase Optimization Plan

## Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ COMPLETED | 23 | Database Indexes, Connection Pooling, ORDER BY RAND() removal, Debug logs, Kafka Reuse, Error Handling, Env Defaults, API Caching, React Memoization, Shared Utils, Event-Driven Sleep, orjson, Vite Compression, Manual Chunk Splitting, SWR/React Query, Docker Build Optimization, Python 3.14 + Node 24 Upgrade, Redis Caching, API Response Compression, Split service_api/app.py, Slow Query Analysis, Query Result Caching, Batch API Requests |
| 🔲 TODO | 0 | All optimizations complete |

---

## ✅ COMPLETED

### 1. Database Indexes
- **File:** `setup/migration_005_indexes.sql`
- **Indexes added:**
  - `device_history(device_id, timestamp)`
  - `config(name)`
  - `personality(type)`
  - `quips(type)`
  - `environment(name)`
  - `calendar_events(end_time)`

### 2. Connection Pooling (service_api)
- **Files created/modified:**
  - `services/common/db_pool.py` (moved to common)
  - `services/service_api/requirements.txt` (+ DBUtils==3.1.0)
  - `services/service_api/Dockerfile` (+ common/)
  - `services/service_api/app.py` (replaced 37 connections)
  - `services/service_api/ha_utils.py` (replaced 3 connections)
  - `services/service_api/st_utils.py` (replaced 3 connections)
- **Pool config:** maxconnections=20, mincached=5, maxcached=10

### 3. ORDER BY RAND() Removal
- `services/service_speak/personality.py` - Uses `random.shuffle()` instead
- `services/service_daemon/alfr3ddaemon.py` - New `get_random_quip()` helper

### 4. Debug Console.log Removal
- `PersonnelRoster.jsx` - Removed 17 debug logs
- `AudioPlayer.jsx` - Removed 10 debug logs
- `Domain.jsx` - Removed 3 debug logs
- `ContainerHealth.jsx` - Removed 1 debug log

### 5. Kafka Producer Reuse (shared common module)
- **Files created/modified:**
  - `services/common/__init__.py` (NEW)
  - `services/common/kafka_pool.py` (NEW) - Singleton producer pool
  - `services/service_api/app.py` - Uses shared get_producer()
  - `services/service_daemon/alfr3ddaemon.py` - Uses shared get_producer()
  - `services/service_daemon/utils/util_routines.py` - Uses shared get_producer()
  - `services/service_device/app.py` - Uses shared get_producer()
  - `services/service_user/app.py` - Uses shared get_producer()
  - `services/service_speak/app.py` - Uses shared get_producer()
  - `services/service_environment/environment.py` - Uses shared get_producer()
  - `services/service_environment/weather_util.py` - Uses shared get_producer()

### 6. Error Handling Improvements
- **Files created:**
  - `services/common/error_handling.py` (NEW) - Common error handling utilities
  - `services/common/__init__.py` (updated)
- **Files improved:**
  - `services/service_api/app.py` - Added specific KafkaError handling
  - `services/service_api/ha_utils.py` - Added pymysql.Error handling with rollback, requests.RequestException
  - `services/service_api/st_utils.py` - Added pymysql.Error handling with rollback, requests.RequestException
  - `services/service_daemon/alfr3ddaemon.py` - Added proper try/finally with rollback in check_gatherings()
  - `services/service_device/app.py` - Added pymysql.Error handling, improved rollback patterns
  - `services/service_device/ha_utils.py` - Added pymysql.Error handling, requests.RequestException
  - `services/service_device/st_utils.py` - Added pymysql.Error handling, requests.RequestException
  - `services/service_user/app.py` - Added KafkaError handling
  - `services/service_user/db_utils.py` - Added pymysql.Error handling
  - `services/service_speak/app.py` - Added pymysql.Error, KafkaError handling
  - `services/service_speak/personality.py` - Added pymysql.Error handling to all functions
  - `services/service_speak/llm_client.py` - Added pymysql.Error handling to all functions
  - `services/service_environment/environment.py` - Added KafkaError, OSError handling
  - `services/service_environment/weather_util.py` - Added KafkaError, OSError handling
  - `services/service_environment/db_utils.py` - Added pymysql.Error handling
  - `services/service_daemon/utils/db_utils.py` - Added pymysql.Error handling
  - `services/service_daemon/utils/gmail_utils.py` - Added OSError handling
  - `services/service_daemon/utils/calendar_utils.py` - Added pymysql.Error handling with rollback
  - `services/service_frontend/app.py` - Added pymysql.Error handling, env variable defaults

### 7. Environment Variable Defaults
- **Files improved:**
  - `services/service_frontend/app.py` - Added os.environ.get() with defaults

### 8. API Response Caching
- **Files created:**
  - `services/common/cache.py` (NEW) - TTL-based in-memory cache utility
  - `services/common/__init__.py` (updated)
- **Endpoints created (5-minute TTL):**
  - `/api/device-types` - Returns list of device types
  - `/api/user-types` - Returns list of user types
  - `/api/states` - Returns list of states
- **Cache config:** 300 second TTL, thread-safe with RLock

### 9. React Component Memoization
- **Files improved:**
  - `ControlBlade.jsx` - Added useCallback for handlers
  - `PersonnelRoster.jsx` - Extracted UserCard/DeviceCard with React.memo, useCallback for all handlers
  - `Blueprint.jsx` - Extracted DeviceIcon/DeviceListItem with React.memo, useMemo for computed values, useCallback for handlers

### 10. Shared Utilities Package
- **Files created:**
  - `services/common/pyproject.toml` (NEW) - Installable package configuration
  - `services/common/setup.py` (NEW) - Setuptools configuration
  - `services/common/db_utils.py` (NEW) - Consolidated from 3 copies
  - `services/common/ha_utils.py` (NEW) - Consolidated from 2 copies
  - `services/common/st_utils.py` (NEW) - Consolidated from 2 copies
- **Files updated:**
  - `services/common/__init__.py` - Added db_utils, ha_utils, st_utils exports
- **Files updated imports:**
  - `services/service_environment/weather_util.py` - Uses common.db_utils
  - `services/service_environment/environment.py` - Uses common.db_utils
  - `services/service_user/app.py` - Uses common.db_utils
  - `services/service_daemon/utils/util_routines.py` - Uses common.db_utils
  - `services/service_api/app.py` - Uses common.ha_utils, common.st_utils
  - `services/service_device/app.py` - Uses common.ha_utils, common.st_utils
- **Requirements updated (added DBUtils, requests):**
  - `services/service_device/requirements.txt`
  - `services/service_environment/requirements.txt`
  - `services/service_user/requirements.txt`
  - `services/service_daemon/requirements.txt`
- **Files deleted (7 duplicates):**
  - `service_environment/db_utils.py`
  - `service_user/db_utils.py`
  - `service_daemon/utils/db_utils.py`
  - `service_api/ha_utils.py`
  - `service_api/st_utils.py`
  - `service_device/ha_utils.py`
  - `service_device/st_utils.py`
- **Total code reduction:** ~1,200 lines of duplicate code eliminated

### 11. Event-Driven Sleep
- **Files improved:**
  - `service_device/app.py` - Replaced iteration with `consumer.poll(timeout_ms=1000)`, added `threading.Event()` for shutdown, exponential backoff for retries
  - `service_user/app.py` - Same pattern as device service
  - `service_environment/environment.py` - Same pattern as device service
  - `service_speak/app.py` - Changed 30s fixed sleep to 1s Event.wait() for faster scheduler response
  - `service_api/tree_of_alfr3d.py` - Added Event.wait() for file watcher
- **Benefits:**
  - Event-driven Kafka message handling (no busy-waiting)
  - Graceful shutdown support via threading.Event
  - Exponential backoff for connection retries (5s → 10s → 20s → 40s → max 60s)
  - Faster scheduler response in speak service (1s vs 30s)

### 12. JSON Serialization (orjson)
- **Files updated:**
  - `service_api/requirements.txt` - Added orjson==3.10.14
  - `service_device/requirements.txt` - Added orjson==3.10.14
  - `service_user/requirements.txt` - Added orjson==3.10.14
  - `service_environment/requirements.txt` - Added orjson==3.10.14
  - `service_speak/requirements.txt` - Added orjson==3.10.14
  - `service_daemon/requirements.txt` - Added orjson==3.10.14
- **Files improved (replaced json with orjson):**
  - `service_api/app.py` - 9 usages (loads for Kafka, DB; dumps for actions)
  - `service_device/app.py` - 2 usages
  - `service_user/app.py` - 4 usages
  - `service_environment/environment.py` - 4 usages
  - `service_environment/weather_util.py` - 2 usages
  - `service_speak/app.py` - 1 usage
  - `service_daemon/alfr3ddaemon.py` - 10 usages
  - `service_daemon/utils/util_routines.py` - 1 usage
  - `common/kafka_pool.py` - serializer
  - `common/ha_utils.py` - 1 usage
- **Benefits:**
  - orjson is 3-10x faster than stdlib json
  - Reduces CPU usage in high-throughput services
  - orjson.dumps() returns bytes directly (no .encode() needed)

### 13. Vite Compression
- **Files:** `services/service_frontend/vite.config.js`, `services/service_frontend/package.json`
- **Package:** `vite-plugin-compression`
- **Config:** Enable gzip and brotli compression
- **Impact:** ~70% smaller bundle transfer size
- **Changes:**
  1. Installed `vite-plugin-compression`
  2. Added gzip and brotli compression to vite.config.js
  3. Updated nginx.conf with `gzip_static on` to serve pre-compressed files
- **Result:** All assets now have .gz and .br versions

### 14. Manual Chunk Splitting
- **File:** `services/service_frontend/vite.config.js`
- **Add:** rollupOptions.manualChunks
- **Split:**
  - `vendor` - react, react-dom, router (157KB)
  - `motion` - framer-motion (100KB)
  - `charts` - recharts, d3 (385KB)
  - `maps` - leaflet, react-leaflet (151KB)
  - `lucide` - icons (8KB)
- **Impact:** Better caching, smaller initial load, parallel loading
- **Result:** Separate chunks for vendor libs, charts, maps, motion, icons

### 15. SWR/React Query for API Caching
- **Package:** `@tanstack/react-query`
- **Impact:** Instant repeat loads, reduced API calls, automatic cache management
- **Changes:**
  1. Installed @tanstack/react-query
  2. Added QueryClientProvider to App.jsx with config (5-min stale, 10-min cache)
  3. Created `services/service_frontend/src/hooks/useApi.js` with hooks for:
     - Routines (query + CRUD mutations)
     - Personality, presets, LLM config
     - Quips (query + CRUD mutations)
     - Integration/IoT status
  4. Updated Routines.jsx to use React Query hooks
- **Result:** Automatic client-side caching with cache invalidation on mutations

---

## 🔲 TODO (Priority Order)

### PHASE 2: BUILD & DEPLOYMENT SPEED (Medium Effort)

#### 16. Docker Build Optimization
- **Files:** All service Dockerfiles, `docker-compose.yml`
- **Changes:**
  - Added BuildKit syntax directive (`# syntax=docker/dockerfile:1`) to all Dockerfiles
  - Added pip cache mount (`--mount=type=cache,target=/root/.cache/pip`) to all Python services
  - Added .dockerignore files to exclude __pycache__, .pyc, tests, .env, etc.
  - Added note in docker-compose.yml to enable BuildKit (`export DOCKER_BUILDKIT=1`)
- **Impact:** 30-50% faster rebuilds (pip packages cached between builds)
- **Result:**
  - All 7 Python Dockerfiles updated with BuildKit cache mounts
  - 2 .dockerignore files created (service_api, service_user)
  - Build verified successful with DOCKER_BUILDKIT=1

#### 17. Python 3.14 + Node 24 Upgrade ✅
- **Files:** All service Dockerfiles
- **Changes:**
  - 6 Python services: `python:3.11.9-slim` → `python:3.14-slim`
  - 1 Node service: `node:20.20.2-alpine` → `node:24-alpine`
  - Standardized all Python services to `python:3.14-slim` (latest stable)
  - Node upgraded to v24 LTS (Active LTS until Apr 2028, replaces EOL v20)
- **Impact:** ~10-15% Python performance boost, Node.js LTS with extended support

---

### PHASE 3: BACKEND DATA HANDLING (Medium-High Effort)

#### 18. Redis Caching Layer ✅
- **Files:** `docker-compose.yml`, `services/common/redis_client.py`, `services/common/cache.py`, `.env.example`, all `requirements.txt`
- **Add:** Redis service to docker-compose.yml
- **Impact:** Cache DB queries, API responses, reduce DB load
- **Status:** ✅ Complete
- **Changes:**
  1. `redis:7-alpine` container in `docker-compose.yml` (lines 35-45)
  2. `services/common/redis_client.py` — singleton Redis client with connection pooling, JSON serialization, in-memory fallback
  3. `services/common/cache.py` — `TTLCache` class using Redis as primary backend, falls back to in-memory when Redis is unavailable
  4. Cache wired into service API via `_get_cached_or_fetch()` in `dependencies.py`:
     - `api:users:{env}` — 120s TTL
     - `api:devices:{env}` — 120s TTL
     - `api:weather` — 300s TTL
     - `api:environment` — 300s TTL
     - `personality:current` — default TTL
     - `personality:presets` — default TTL
     - `personality:context:{env}` — 300s TTL
     - `personality:llm-config` — 600s TTL
     - `quips:all` — default TTL
     - Routines list — default TTL
  5. Cache invalidation on writes for devices, personality, quips, routines
  6. `redis[hiredis]>=5.0.0` added to all 6 Python service requirements.txt
  7. `REDIS_HOST=redis`, `REDIS_PORT=6379` added to `.env.example`
  8. `redis_client.py` switched from stdlib `json` to `orjson` for consistency

#### 19. API Response Compression
- **File:** `services/service_api/app.py`
- **Add:** uvicorn gzip middleware
- **Impact:** 50-70% smaller API responses
- **Steps:**
  1. Add uvicorn.middleware.gzip.GzipMiddleware
  2. Configure compression level

#### 20. Split service_api/app.py (2144 → 164 lines) ✅
- **New Structure:**
  - `models.py` — 20 Pydantic models (137 lines)
  - `dependencies.py` — shared state, helpers, env vars (211 lines)
  - `routes/users.py` — user CRUD (157 lines)
  - `routes/devices.py` — device CRUD + types + states + history (371 lines)
  - `routes/quips.py` — quips CRUD (70 lines)
  - `routes/environment.py` — weather, environment, calendar (189 lines)
  - `routes/integrations.py` — calendar/gmail sync (62 lines)
  - `routes/audio.py` — audio file serving (32 lines)
  - `routes/events.py` — events + SA (17 lines)
  - `routes/containers.py` — container metrics + background task (113 lines)
  - `routes/routines.py` — routines CRUD + Kafka execution (170 lines)
  - `routes/personality.py` — personality, presets, context, LLM config (205 lines)
  - `routes/iot.py` — HA + SmartThings + unified IoT (374 lines)
- **Impact:** app.py: 2144 → 164 lines, each route file focused on single domain
- **Status:** ✅ Complete — all 15 files pass syntax checks

---

### PHASE 4: DATABASE OPTIMIZATION

#### 21. Slow Query Analysis ✅
- **Tool:** MySQL EXPLAIN, slow_query_log
- **Status:** ✅ Complete
- **Changes:**
  1. `setup/my.cnf` — MySQL config enabling slow_query_log (long_query_time=1s, log_queries_not_using_indexes)
  2. `docker-compose.yml` — mounts `./setup/my.cnf` into mysql container at `/etc/mysql/conf.d/slow_query.cnf`
  3. `setup/migration_010_slow_query_indexes.sql` — 8 new indexes covering identified query patterns:
     - `device(MAC)` — heavy WHERE MAC lookups
     - `device(last_online)` — offline-detection range scan
     - `device(user_id)` — JOINs with user table
     - `user(username)` — WHERE username lookups
     - `user(state)` — online-user filtering
     - `user(last_online)` — ORDER BY last_online DESC
     - `personality(type, environment_id)` — compound index for filtered+ordered queries
     - `calendar_events(start_time)` — range queries (was missing, DATE() wrapper made index unusable)
  4. `services/service_api/routes/environment.py:99-101` — Changed `WHERE DATE(start_time) = %s` to `WHERE start_time >= %s AND start_time < %s + INTERVAL 1 DAY` so the new start_time index is usable
  5. Modernized 4 implicit comma-join queries to explicit JOIN syntax:
     - `services/service_device/app.py` — `FROM states s, device_types dt, user u, environment e` → explicit JOINs
     - `services/service_user/app.py` — same pattern for user setup
     - `services/common/ha_utils.py` — same pattern for device linking
     - `services/common/st_utils.py` — same pattern for SmartThings linking

#### 22. Query Result Caching (Expand existing cache.py) ✅
- **Files:** `services/common/cache.py`
- **Status:** ✅ Complete (covered by Redis Caching task #18)
- **Changes:**
  1. Redis cache now used for personality, presets, quips, device lists, config endpoints
  2. Cache invalidation triggers on data changes

---

### LOW PRIORITY

#### 23. Batch API Requests
- Create `/api/users-with-devices` endpoint
- Reduce sequential fetches in PersonnelRoster

---

## Implementation Progress

| # | Optimization | Phase | Status | Impact | Effort |
|---|-------------|-------|--------|--------|--------|
| 1 | Database Indexes | - | ✅ Done | High | Low |
| 2 | Connection Pooling | - | ✅ Done | High | Medium |
| 3 | ORDER BY RAND() | - | ✅ Done | Medium | Low |
| 4 | Debug Logs | - | ✅ Done | Low | Low |
| 5 | Kafka Reuse | - | ✅ Done | Medium | Medium |
| 6 | Error Handling | - | ✅ Done | Medium | Medium |
| 7 | Env Defaults | - | ✅ Done | Low | Low |
| 8 | API Caching | - | ✅ Done | Medium | Low |
| 9 | React Memoization | - | ✅ Done | Medium | Low |
| 10 | Shared Utils | - | ✅ Done | Medium | Medium |
| 11 | Event-Driven Sleep | - | ✅ Done | Low | Medium |
| 12 | orjson | - | ✅ Done | Low | Low |
| 13 | Vite Compression | 1 | ✅ Done | High | Low |
| 14 | Manual Chunk Splitting | 1 | ✅ Done | Medium | Low |
| 15 | SWR/React Query | 1 | ✅ Done | Medium | Medium |
| 16 | Docker Build Optimization | 2 | ✅ Done | Medium | Medium |
| 17 | Python 3.10+ Upgrade | 2 | ✅ Done | Medium | High |
| 18 | Redis Caching | 3 | ✅ Done | High | Medium |
| 19 | API Response Compression | 3 | ✅ Done | Medium | Low |
| 20 | Split service_api/app.py | 3 | ✅ Done | Medium | High |
| 21 | Slow Query Analysis | 4 | ✅ Done | Medium | Medium |
| 22 | Query Result Caching (Redis) | 4 | ✅ Done | Medium | Low |
| 23 | Batch API Requests | - | ✅ Done | Low | Medium |

---

## Notes

- Test database migration before deploying
- Benchmark connection pooling (before/after)
- Monitor Kafka consumer lag
- Phase 1 items should be done first (highest impact, lowest effort)
- Python 3.14 + Node 24 upgrade completed with standardized base images across all services
