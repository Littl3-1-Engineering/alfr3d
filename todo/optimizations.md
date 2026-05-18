# ALFR3D Codebase Optimization Plan

## Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ COMPLETED | 16 | Database Indexes, Connection Pooling, ORDER BY RAND() removal, Debug logs, Kafka Reuse, Error Handling, Env Defaults, API Caching, React Memoization, Shared Utils, Event-Driven Sleep, orjson, Vite Compression, Manual Chunk Splitting, SWR/React Query, Docker Build Optimization |
| 🔲 TODO | 4 | Python 3.10+ Upgrade, Redis Caching, Split service_api/app.py, Slow Query Analysis |

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

#### 17. Python 3.10+ Upgrade
- **Files:** All service Dockerfiles, requirements.txt
- **Changes:**
  - Change base image from python:3.9-slim to python:3.10-slim or python:3.11-slim
  - Update pinned package versions (e.g., requests==2.32.5)
  - Test all services
- **Impact:** ~10% performance boost, access to newer packages
- **Steps:**
  1. Audit all requirements.txt files for version constraints
  2. Update Dockerfiles to python:3.10-slim
  3. Fix any version compatibility issues
  4. Test each service individually
  5. Run full integration test suite

---

### PHASE 3: BACKEND DATA HANDLING (Medium-High Effort)

#### 18. Redis Caching Layer
- **Files:** `docker-compose.yml`, `services/common/`
- **Add:** Redis service to docker-compose.yml
- **Impact:** Cache DB queries, API responses, reduce DB load
- **Steps:**
  1. Add Redis container to docker-compose.yml
  2. Create Redis client wrapper in common/
  3. Cache personality, quips, config endpoints
  4. Add cache invalidation on writes

#### 19. API Response Compression
- **File:** `services/service_api/app.py`
- **Add:** uvicorn gzip middleware
- **Impact:** 50-70% smaller API responses
- **Steps:**
  1. Add uvicorn.middleware.gzip.GzipMiddleware
  2. Configure compression level

#### 20. Split service_api/app.py (1986 lines → modular)
- **New Structure:**
  - `services/service_api/routes/users.py`
  - `services/service_api/routes/devices.py`
  - `services/service_api/routes/personality.py`
  - `services/service_api/routes/routines.py`
  - `services/service_api/routes/integrations.py`
  - `services/service_api/routes/__init__.py`
- **Impact:** Easier to maintain, test, optimize, cache
- **Steps:**
  1. Create routes/ directory and __init__.py
  2. Extract route handlers to separate files
  3. Register blueprints in app.py
  4. Test all endpoints still work

---

### PHASE 4: DATABASE OPTIMIZATION

#### 21. Slow Query Analysis
- **Tool:** MySQL EXPLAIN, slow_query_log
- **Steps:**
  1. Enable slow query log in MySQL config
  2. Identify slow queries (personality, quips, calendar)
  3. Add indexes where missing
  4. Optimize JOINs

#### 22. Query Result Caching (Expand existing cache.py)
- **Files:** `services/common/cache.py` (exists, expand usage)
- **Steps:**
  1. Add cache for personality, presets, quips endpoints
  2. Add cache for device lists
  3. Add cache invalidation triggers on data changes

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
| 17 | Python 3.10+ Upgrade | 2 | 🔲 TODO | Medium | High |
| 18 | Redis Caching | 3 | 🔲 TODO | High | Medium |
| 19 | API Response Compression | 3 | ✅ Done | Medium | Low |
| 20 | Split service_api/app.py | 3 | 🔲 TODO | Medium | High |
| 21 | Slow Query Analysis | 4 | 🔲 TODO | Medium | Medium |
| 22 | Query Result Caching | 4 | ✅ Done | Medium | Low |
| 23 | Batch API Requests | - | ✅ Done | Low | Medium |

---

## Notes

- Test database migration before deploying
- Benchmark connection pooling (before/after)
- Monitor Kafka consumer lag
- Phase 1 items should be done first (highest impact, lowest effort)
- Python 3.10+ upgrade is in progress via separate task
