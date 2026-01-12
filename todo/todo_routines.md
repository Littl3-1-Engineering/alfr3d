# Plan to Implement Routine Management System in Frontend

## Current State
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
