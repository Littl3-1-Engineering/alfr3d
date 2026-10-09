# LF-0: 730-day retention and history capture for every SA variable

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-0

## Status: 🔲 Not started (planned 2026-10-09)

## Why

The 2026-09-13 retention change (migration 039, see
[todo_sa_data_retention_3yr.md](todo_sa_data_retention_3yr.md)) was assumed to cover all SA
variables. It covered four event-log tables. This phase closes the rest so every SA variable is
kept for 2 years in MySQL. Data that has already been discarded (calendar events older than 24 h
after their end, weather history, `device_history` older than 180 days) **cannot be recovered**.

## Scope

Next free numbers: raw SQL `migration_043_*`, alembic `0048_*`. Same raw-SQL-plus-alembic-wrapper
pattern as 039/0042, retention as MySQL EVENTs.

- [ ] **`device_history` → 730 days.** Recreate `maintain_device_history_partitions_event` with
      `CALL maintain_device_history_partitions(730, 3)` (migration 025 currently passes 180).
      Check first who owns the existing event on the NUC: the retention doc notes this table's
      original event was created by `root`/`SYSTEM_USER`, unlike the others, so a migration user
      may not be able to drop it. ~4.7 GB at 2 years at the measured ~30.4k rows/day; 37 GB free.
- [ ] **`environment_history`** (new table): one row per weather/forecast update with the same
      columns `weather_util.py` writes (`services/service_environment/weather_util.py:215` and
      `:252`), plus `recorded_at`. Insert alongside both UPDATEs. 730-day EVENT.
- [ ] **`calendar_events`**: change `cleanup_calendar_events_event` (`createTables.sql:305`) from
      `24 HOUR` to `730 DAY`. Checked: `sync_calendar()` only deletes rows inside its forward
      window (`end_time >= now`, `services/service_daemon/utils/calendar_utils.py:255`), so past
      events survive. Check every reader of `calendar_events` for queries that assume only
      current/future rows exist (e.g. `check_departure_anomaly`'s "event covers now" check is
      fine; anything doing an unbounded `SELECT` is not).
- [ ] **`listening_history`**: add a 730-day EVENT on `played_at`.
- [ ] **`device_command_history`**: no writer exists (IoT commands go to `household_events`).
      Drop the table and its 180-day event, and remove the leftover DELETE in
      `services/service_api/routes/iot.py:723` (the per-device delete endpoint).
- [ ] Add `environment_history`, `calendar_events`, `listening_history` and
      `smarthome_sensor_history` to `record_sa_storage_metrics_proc`.
- [ ] Update [todo_sa_data_retention_3yr.md](todo_sa_data_retention_3yr.md)'s "What was
      deliberately not touched" section and the Notion Timeline row to say what changed.

## Verify

- Against local MySQL 8 (`test-mysql` in `docker-compose.yml`): upgrade, `SHOW CREATE EVENT` for
  each window, downgrade, upgrade again.
- Seed stale and fresh rows; confirm each EVENT body's DELETE removes only the stale ones.
- After deploy: `environment_history` gains a row after `update_weather` runs; `SHOW EVENTS` on
  the NUC lists every window at 730 days.
- Take a `mysqldump` backup on the NUC before migrating.
