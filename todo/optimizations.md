# ALFR3D Codebase Optimization Plan

## Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ COMPLETED | 12 | Database Indexes, Connection Pooling, ORDER BY RAND() removal, Debug logs, Kafka Reuse, Error Handling, Env Defaults, API Caching, React Memoization, Shared Utils, Event-Driven Sleep, orjson |
| 🔲 TODO | 2 | Batch Requests, Bundle Splitting |

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

---

## 🔲 TODO (Priority Order)

### LOW PRIORITY

#### 11. Batch API Requests
- Create `/api/users-with-devices` endpoint
- Reduce sequential fetches in PersonnelRoster

#### 12. Frontend Bundle Size
- Add code-splitting for large components (Nexus.jsx, Matrix.jsx, Core.jsx)

---

## Implementation Progress

| # | Optimization | Status | Impact |
|---|-------------|--------|--------|
| 1 | Database Indexes | ✅ Done | High |
| 2 | Connection Pooling | ✅ Done | High |
| 3 | ORDER BY RAND() | ✅ Done | Medium |
| 4 | Debug Logs | ✅ Done | Low |
| 5 | Kafka Reuse | ✅ Done | Medium |
| 6 | Error Handling | ✅ Done | Medium |
| 7 | Env Defaults | ✅ Done | Low |
| 8 | API Caching | ✅ Done | Medium |
| 9 | React Memoization | ✅ Done | Medium |
| 10 | Shared Utils | ✅ Done | Medium |
| 11 | Event-Driven Sleep | ✅ Done | Low |
| 12 | orjson | ✅ Done | Low |
| 13 | Batch Requests | 🔲 TODO | Low |
| 14 | Bundle Splitting | 🔲 TODO | Low |

---

## Notes

- Test database migration before deploying
- Benchmark connection pooling (before/after)
- Monitor Kafka consumer lag
