# Plan to Implement Routine Management System in Frontend

## Status: ✅ COMPLETE

All phases below (database schema, backend API, daemon execution, frontend UI) are implemented — see "Implementation Progress" for what actually shipped. The original "Current State"/"Implementation Plan" section above it describes the pre-implementation starting point and is kept for historical context only.

## Original Current State (pre-implementation, now historical)
- DB stores basic routines (time-based, one-shot per day).
- Daemon checks and triggers via `util_routines.py`, but no UI or custom actions.

## Implementation Plan
1. **UI Design**:
   - New "Routines" page with list, create/edit form.
   - Support time-based triggers (daily/weekly), actions (speak, email, lights), drag-and-drop ordering.

2. **Backend**:
   - Extend `routines` table with `recurrence`, `actions` (JSON).
   - Add API: `GET/POST/PUT/DELETE /api/routines`.
   - Update `service_daemon` to dynamically schedule and execute actions via Kafka.

3. **Execution**:
   - Build on 'schedule' library; future migrate to Celery for complexity.
   - Actions map to Kafka topics (e.g., "speak", "environment").

4. **User Workflow**:
   - Create/edit routines via form; validate and store.
   - Daemon reloads schedules; executes at triggers.

5. **Testing**:
   - Add UI dry-run; unit tests for logic.

## Challenges
- Dynamic scheduling, multi-step actions, scalability.

---

## Implementation Progress

### Phase 1: Database Schema ✓
- Created `setup/migration_003_routines.sql`:
  - Added `recurrence` column (ENUM: once, daily, weekly, weekdays)
  - Added `actions` column (JSON)
  - Added `last_run` column (TIMESTAMP)
  - Added index for faster lookups

### Phase 2: Backend API ✓
- Endpoints now live in `services/service_api/routes/routines.py` (registered via `app.include_router()` in `app.py`), migrated from Flask to FastAPI since this was first written:
  - `GET /api/routines` - List all routines
  - `POST /api/routines` - Create routine
  - `PUT /api/routines/{routine_id}` - Update routine
  - `DELETE /api/routines/{routine_id}` - Delete routine
  - `POST /api/routines/{routine_id}/run` - Execute routine manually

### Phase 3: Daemon Execution ✓
- Updated `services/service_daemon/utils/util_routines.py`:
  - Added Kafka producer for sending actions
  - Added `execute_actions()` function to parse and execute actions
  - Updated `check_routines()` to handle recurrence (daily, weekdays, weekly)
  - Executes actions via Kafka topics (speak, device, email, scene)

### Phase 4: Frontend ✓
- Updated `services/service_frontend/src/components/Routines.jsx`:
  - Connected to API (GET/POST/PUT/DELETE)
  - Routine list with name, time, recurrence display
  - Create/edit form with name, time, recurrence, enabled
  - Action builder supporting speak, device, email actions
  - Run and delete buttons for each routine
  - Manual execution via `/api/routines/<id>/run`

### Supported Action Types
```json
[
  {"type": "speak", "params": {"text": "Good morning!"}},
  {"type": "device", "params": {"device_id": 1, "action": "on"}},
  {"type": "email", "params": {"to": "...", "subject": "...", "body": "..."}},
  {"type": "scene", "params": {"scene_id": "movie"}}
]
```

### Implementation Complete ✓
- All phases completed and tested
- Migration applied: `migration_003_routines.sql`
- Tested end-to-end: routine creation and execution working
