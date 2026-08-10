# ALFR3D Codebase Optimization & Improvement Plan v2

## Priority Key

| Icon | Meaning |
|------|---------|
| 🔴 | Critical (bug, crash, data loss) |
| 🟠 | High (performance, security, reliability) |
| 🟡 | Medium (maintainability, consistency) |
| 🔵 | Low (cleanup, nice-to-have) |

---

## 🔴 CRITICAL BUGS

### 1. `self.check_emails` Missing `()` — Method Never Called
- **File:** `services/service_daemon/alfr3ddaemon.py:451`
- **Issue:** `self.check_emails` without `()` is a method reference, not a call. The `perform_waking_hours_tasks()` method never actually checks emails.
- **Fix:** Change `self.check_emails` → `self.check_emails()` on line 451
- **Impact:** Gmail checking during waking hours is silently broken
- **Status: ✅ FIXED** (`alfr3ddaemon.py:451` now calls `self.check_emails()`)

### 2. Kafka Message Sent as Python Dict (Unserialized)
- **File:** `services/service_speak/app.py:206,232-233`
- **Issue:** `p.send("event-stream", event)` sends a raw Python dict. `kafka-python 2.0.2` expects bytes/serializable. Every other service uses `orjson.dumps()` before `p.send()`.
- **Fix:** Wrap each `p.send()` call with `orjson.dumps()` (lines 206, 232, 233)
- **Impact:** Event-stream and personality messages from speak service are sent incorrectly; consumers may silently drop them
- **Status: ✅ FIXED** (all three `p.send()` calls in `send_event()` / `send_personality_state()` wrap payloads in `orjson.dumps()`)

---

## 🟠 HIGH PRIORITY

### 3. Kafka Client Fragmentation — Three Different Libraries
- **Files:**
  - `services/service_speak/requirements.txt` — `kafka-python==2.0.2` (older, different API)
  - All other services — `kafka-python-ng==2.2.3`
  - `tests/requirements.txt` — `confluent-kafka==2.6.1`
  - `services/common/pyproject.toml` — `confluent-kafka>=2.0.0`
- **Issues:**
  - `kafka-python 2.0.2` has different serialization expectations than `kafka-python-ng`
  - `confluent-kafka` in tests means test fixtures don't match production Kafka client
  - `pyproject.toml` lists wrong kafka dependency
- **Fix:** Standardize all services + tests on `kafka-python-ng==2.2.3`. Update `pyproject.toml` to match.
- **Impact:** Eliminates serialization bugs, test fidelity, simplified dependency management
- **Status: ✅ FIXED** (`service_speak/requirements.txt` → `kafka-python-ng==2.2.3`, `tests/requirements.txt` → `kafka-python-ng==2.2.3`, `pyproject.toml` → `kafka-python-ng>=2.2.3`)

### 4. `common/db_utils.py` Bypasses Connection Pool
- **File:** `services/common/db_utils.py:20-21`
- **Issue:** `get_db_connection()` uses `pymysql.connect()` directly instead of `get_connection()` from `db_pool.py`. This means 5+ service modules that use `db_utils.get_db_connection()` create unpooled connections.
- **Fix:** Replace with `from .db_pool import get_connection`
- **Impact:** Every call to `get_env_timezone()`, `check_mute_optimized()`, etc. opens a new TCP connection to MySQL instead of reusing from pool
- **Status: ✅ FIXED** (`common/db_utils.py` now imports `get_connection()` from `.db_pool`; also added `wait_for_db()` retry helper)

### 5. `service_speak/personality.py` Creates Raw DB Connections
- **File:** `services/service_speak/personality.py:20-26`
- **Issue:** `get_db_connection()` uses `pymysql.connect()` directly. This file has ~15 functions that each open fresh unpooled connections.
- **Fix:** Replace with pooled `get_connection()` from `common/`
- **Impact:** Every speak service personality query opens a new MySQL connection
- **Status: ✅ FIXED** (`get_db_connection()` returns `get_connection()` from `common`)

### 6. `service_speak/llm_client.py` Creates Raw DB Connections
- **File:** `services/service_speak/llm_client.py:16-22`
- **Issue:** Same pattern — `pymysql.connect()` directly
- **Fix:** Use pooled connection from `common/`
- **Status: ✅ FIXED** (`get_db_connection()` returns `get_connection()` from `common`)

### 7. `service_frontend/app.py` Creates Raw DB Connections
- **File:** `services/service_frontend/app.py:30-32`
- **Issue:** `pymysql.connect()` on every `/api/users` request. This service already has access to `common/` via sys.path.
- **Fix:** Import and use `get_connection()` from `common`
- **Impact:** Each frontend page load opens a new MySQL connection (no pooling, no reuse)
- **Status: ✅ FIXED** (`service_frontend/app.py` now uses `get_connection()` from `common`)

### 8. Unused `socket.io-client` Dependency
- **File:** `services/service_frontend/package.json:27`
- **Issue:** `socket.io-client` listed as dependency but never imported anywhere in `src/`. The frontend uses a custom `WebSocket` client in `src/utils/socket.js`.
- **Fix:** Remove `"socket.io-client": "^4.8.1"` from dependencies
- **Impact:** Reduces build size and removes unnecessary dependency
- **Status: ✅ FIXED** (removed from `package.json`; `vitest`, `jsdom`, `@testing-library/*` added for #13)

---

## 🟡 MEDIUM PRIORITY

### 9. K8s Service Port Mismatch (5002 vs 5001)
- **File:** `k8s/service-api-service.yaml:9`
- **Issue:** Service port is `5002` targeting `targetPort: 5001`, but the app runs on port `5001`. Verify ingress routes point correctly.
- **Fix:** Change service port to `5001` (or verify `5002` → `5001` mapping is intentional and working)
- **Impact:** K8s deployment traffic to API gateway may fail
- **Status: ✅ FIXED** (`k8s/service-api-service.yaml` and `k8s/ingress.yaml` both now use port `5001`)

### 10. `pyproject.toml` References Wrong Kafka Client
- **File:** `services/common/pyproject.toml:13`
- **Issue:** Lists `confluent-kafka>=2.0.0` as dependency but code uses `kafka-python-ng`
- **Fix:** Change to `kafka-python-ng>=2.2.3` or remove (services install their own)
- **Impact:** If someone installs `alfr3d-common` directly, they get wrong kafka dependency
- **Status: ✅ FIXED** (`pyproject.toml` now lists `kafka-python-ng>=2.2.3`)

### 11. `pyproject.toml` Python Version Constraint Stale
- **File:** `services/common/pyproject.toml:9`
- **Issue:** `requires-python = ">=3.9"` but all deployment uses Python 3.14
- **Fix:** Update to `>=3.11` to match reality
- **Status: ✅ FIXED** (`requires-python = ">=3.11"`)

### 12. No CI/CD Pipeline
- **Issue:** No GitHub Actions, GitLab CI, or other CI pipeline exists. Only pre-commit hooks enforce quality locally.
- **Recommendation:** Add GitHub Actions workflow for lint, test, build, and optional deploy
- **Status: ✅ DONE** (`.github/workflows/ci.yml` added with frontend lint/test/build + backend unit/integration jobs)

### 13. Minimal Frontend Test Coverage
- **Issue:** Only `App.test.jsx` exists (basic render test). No tests for components, hooks, or WebSocket client.
- **Recommendation:** Add tests for `useApi` hooks, `socket.js`, and core components
- **Status: ✅ DONE** (5 test files, 29 tests passing: `App.test.jsx`, `AudioPlayer.test.jsx`, `ErrorBoundary.test.jsx`, `hooks/useApi.test.jsx`, `utils/socket.test.js`; vitest + jsdom + testing-library added)

### 14. Frontend `console.log` in Production WebSocket Code
- **File:** `services/service_frontend/src/utils/socket.js:15,17,23,29,35,45,53`
- **Issue:** 7 `console.log` calls in production code
- **Recommendation:** Replace with a logger wrapper that respects `NODE_ENV`
- **Status: ✅ FIXED** (`socket.js` now uses a DEV-gated `logger` wrapper)

### 15. Missing `.dockerignore` Files
- **Issue:** Only 2/7 services have `.dockerignore` files. Others include `__pycache__`, `.pyc`, etc. in build context.
- **Fix:** Add `.dockerignore` to `service_device`, `service_environment`, `service_speak`, `service_daemon`, `service_frontend`
- **Status: ✅ FIXED** (all 7 services now have `.dockerignore`)

---

## 🔵 LOW PRIORITY

### 16. `maps_utils.py` Placeholder Implementation
- **File:** `services/service_daemon/utils/maps_utils.py`
- **Issue:** Returns hardcoded fuel cost ($5.00) and departure time (15 min before event). Google Maps API key env var exists but code is not integrated.
- **Recommendation:** Either implement real Google Maps Directions API or remove placeholder
- **Status: ✅ FIXED** — real Google Maps Directions API integration (via existing `googlemaps` dep): duration-based departure time, distance-based fuel cost, graceful placeholder fallback when `GOOGLE_MAPS_API_KEY` is unset

### 17. Hardcoded Values in Service Code
- **Examples:**
  - `service_device/app.py` — `"192."` and `"10."` IP range checks
  - `service_user/app.py` — Hardcoded user type names
  - `common/ha_utils.py:16-17` — `if MYSQL_HOST == "mysql": MYSQL_HOST = "mysql"` (no-op)
- **Recommendation:** Move to config/env vars or DB lookup
- **Status: ✅ FIXED** — LAN IP prefixes now configurable via `LAN_IP_PREFIXES` env var (`service_device/app.py`, default `192.,10.`; documented in `.env.example`). The `ha_utils.py` no-op was removed during the pool migration. User type names remain DB-domain values used in SQL lookups (not config).

### 18. Version Pinning Inconsistencies
- **Issues:**
  - `service_speak/requirements.txt`: `pymysql==1.1.1` (pinned), others: unpinned
  - `service_speak/requirements.txt`: `kafka-python==2.0.2`, others: `kafka-python-ng==2.2.3`
- **Recommendation:** Standardize pinning strategy across all services
- **Status: ✅ FIXED** — all 6 service `requirements.txt` now pinned consistently (`kafka-python-ng==2.2.3`, `pymysql==1.1.2`, `DBUtils==3.1.0`, `orjson==3.11.9`, `cryptography==48.0.1`, `requests==2.33.0`, `redis[hiredis]>=5.0.0`)

### 19. Frontend Dockerfile — Multi-Stage Build
- **File:** `services/service_frontend/Dockerfile`
- **Issue:** Single stage builds and serves everything. `serve` installed globally at runtime.
- **Recommendation:** Split into build stage + run stage for smaller final image
- **Status: ✅ FIXED** — split into `build` (Node 24, `npm ci`, `npm run build`) + runtime stage that copies only `dist/`

### 20. No Alembic / Migration Framework
- **Issue:** SQL migrations are hand-written `.sql` files in `setup/migration_*.sql` (10 migrations). No automated tracking of which migrations have been applied.
- **Recommendation:** Adopt Alembic for schema migrations with version tracking
- **Status: ✅ DONE** — Alembic scaffold in `setup/migrations/` (chained revisions `0001`→`0010` wrapping all raw `.sql` files via `run_sql.py`; baseline from `createTables.sql`). Wired in:
  - `docker-compose.yml` `migrate` service — one-shot `alembic upgrade head`, waits for healthy MySQL, runs before services
  - `setup/migrations/Dockerfile` — build context `./setup`, installs `alembic==1.18.5` + `pymysql`
  - CI job `migrations` — runs the full chain against a clean MySQL, asserts `alembic current` = `0010`
  - Verified end-to-end: clean DB → upgrade chain → downgrade/upgrade round-trip → idempotent re-runs
- **Remaining:** run `alembic stamp head` against the live DB once (existing deployments already have the schema) before relying on `migrate` for new changes
  - ✅ DONE (2026-08-07) — live DB at `alfr3d_db` stamped/upgraded to `0017` via `docker compose run --rm migrate`; pending IoT cleanup (`0017`) applied. `0001_baseline` now skips `createTables.sql` when the base schema already exists (was failing with `1050 Table 'quips' already exists`), so `migrate` is idempotent on existing DBs.

---

## Summary

| Priority | Count | Key Items |
|----------|-------|-----------|
| 🔴 Critical | 2 | `check_emails` bug, unserialized Kafka messages — ✅ both fixed |
| 🟠 High | 6 | Kafka fragmentation, 4 unpooled DB modules, unused dep — ✅ all fixed |
| 🟡 Medium | 7 | K8s port, pyproject stale, no CI, frontend tests, console.log, missing .dockerignore — ✅ all fixed |
| 🔵 Low | 5 | maps placeholder ✅, hardcoded values ✅, version pinning ✅, multi-stage ✅, Alembic ✅ |

**Total: 20 items — all complete.**
