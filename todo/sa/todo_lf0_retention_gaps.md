# LF-0: 730-day retention and history capture for every SA variable

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-0

## Status: 🟢 Deployed to the production NUC 2026-10-09 (migration 043 / alembic 0048)

Backup first: `~/db_backups/alfr3d_backup_20261009_162435_pre_0048.sql.gz` (full `mysqldump`
with routines, events and triggers). Every SA retention window is now 730 days and every event is
owned by `user@%`. `environment_history` recorded its first live `weather` and `forecast` rows
the same evening.

## Why

The 2026-09-13 retention change (migration 039, see
[todo_sa_data_retention_3yr.md](todo_sa_data_retention_3yr.md)) was assumed to cover all SA
variables. It covered four event-log tables. This phase closes the rest so every SA variable is
kept for 2 years in MySQL. Data that has already been discarded (calendar events older than 24 h
after their end, weather history, `device_history` older than 180 days) **cannot be recovered**.

## Scope

Next free numbers: raw SQL `migration_043_*`, alembic `0048_*`. Same raw-SQL-plus-alembic-wrapper
pattern as 039/0042, retention as MySQL EVENTs.

- [x] **`device_history` → 730 days.** Recreate `maintain_device_history_partitions_event` with
      `CALL maintain_device_history_partitions(730, 3)` (migration 025 currently passes 180).
      Check first who owns the existing event on the NUC: the retention doc notes this table's
      original event was created by `root`/`SYSTEM_USER`, unlike the others, so a migration user
      may not be able to drop it. ~4.7 GB at 2 years at the measured ~30.4k rows/day; 37 GB free.
- [x] **`environment_history`** (new table): one row per weather/forecast update with the same
      columns `weather_util.py` writes (`services/service_environment/weather_util.py:215` and
      `:252`), plus `recorded_at`. Insert alongside both UPDATEs. 730-day EVENT.
- [x] **`calendar_events`**: change `cleanup_calendar_events_event` (`createTables.sql:305`) from
      `24 HOUR` to `730 DAY`. Checked: `sync_calendar()` only deletes rows inside its forward
      window (`end_time >= now`, `services/service_daemon/utils/calendar_utils.py:255`), so past
      events survive. Check every reader of `calendar_events` for queries that assume only
      current/future rows exist (e.g. `check_departure_anomaly`'s "event covers now" check is
      fine; anything doing an unbounded `SELECT` is not).
- [x] **`listening_history`**: add a 730-day EVENT on `played_at`.
- [x] **`device_command_history`**: dropped by 0048 because it had no writer, then **restored
      the same day as a real command log** (migration 044 / alembic 0049, see below). Dropping it
      was the wrong call: the data it was meant to hold is a learning signal.
- [x] Add `environment_history`, `calendar_events`, `listening_history` and
      `smarthome_sensor_history` to `record_sa_storage_metrics_proc`.
- [x] Update [todo_sa_data_retention_3yr.md](todo_sa_data_retention_3yr.md)'s "What was
      deliberately not touched" section and the Notion Timeline row to say what changed.

## Verify

- [x] `mysqldump` backup on the NUC before migrating.
- [x] Rehearse on a copy restored from that backup (never a freshly seeded DB): blocked run,
      upgrade, `information_schema.EVENTS` for each window, downgrade, upgrade again.
- [x] After deploy: `environment_history` gains rows after a weather/forecast update; every event
      on the NUC is at 730 days.
- [ ] Not done: exercising each EVENT's DELETE against real stale rows. None exist yet (the
      oldest SA rows are months inside 730 days), and the bodies follow migration 039's pattern
      unchanged. Confirm from `sa_storage_metrics` once the first table crosses 730 days.

## What actually happened (2026-10-09)

- **A second 180-day delete was hiding.** Besides the partition event, a legacy
  `cleanup_device_history_event` (DEFINER `root@%`, from `createTables.sql`) was still running a
  daily `DELETE ... INTERVAL 180 DAY`. Migration 0027 had left it in place as "harmless", which
  was true only while partitions also stopped at 180 days. Raising the partitions alone would
  have changed nothing. The same was true of `cleanup_calendar_events_event` (root) and
  `cleanup_device_command_history_event` (root@localhost).
- **Root-owned events.** The migration account can't drop them (needs `SYSTEM_USER`, MySQL
  error 1227). Migration 0048 tries first and, if blocked, stops **before changing anything**
  with instructions to run `setup/drop_root_owned_events.sql` as root and re-run. Where
  createTables.sql was loaded through alembic as `user` (0001_baseline), the events are
  `user`-owned and the drop just works; installs set up with the older root flow need the root
  script once.
- **No trigger for weather history.** Binary logging is on with
  `log_bin_trust_function_creators=0`, so `user` can't create triggers. The snapshot is written
  by `record_environment_history()` in `weather_util.py` right after each weather/forecast
  UPDATE commits, in its own commit, so a failed history write never undoes the weather update.
- **Rehearsed on a restored copy first, not a seeded DB.** The pre-migration dump was restored
  into a throwaway `mysql:8.0` container (no published port, removed afterwards), and the real
  migrate image was run against it as `user`: blocked-run (schema untouched at 0047), root fix,
  upgrade, downgrade, upgrade again. `device_history` row count was identical throughout.
- **Production**: fresh backup → `drop_root_owned_events.sql` as root → `docker compose
  --profile test run --rm migrate` (0047 → 0048) → rebuilt and restarted `service-api` and
  `service-environment` → triggered `check weather` / `check forecast` on the `environment`
  Kafka topic and confirmed two `environment_history` rows. Side effect: the manual `check
  weather` also spoke the weather aloud.
- **Not recoverable**: weather history before 2026-10-09, calendar events that ended more than
  24 h before the migration, `device_history` before June 2026 (earliest surviving partition is
  `p_2026_06`). Nothing has been lost from `device_history` since partitioning, because the
  earliest partition was still inside 180 days.
- **Disk**: 24 GB free on the NUC on 2026-10-09 (down from 37 GB on 09-13).
  `device_history` at ~30k rows/day reaches roughly 4.7 GB at 730 days, so watch
  `sa_storage_metrics` and the 78% disk usage.
- Unit suite: 677 passed (non-integration, run in a scratch venv from `tests/requirements.txt`,
  with the test-DB env pointed at an unreachable port so nothing could touch production).

## device_command_history restored as a command log (2026-10-09, migration 044 / alembic 0049)

Athos questioned the drop: command history is SA data. `household_events` keeps only a collapsed
verb per command (`set_brightness`, `set_temperature`, `lock`, `volume_set` all become `set`), has
no payload column, records successes only, and the per-source control endpoints
(`/iot/ha/.../control`, `/iot/st/.../control`, `/iot/esphome/.../control`) recorded nothing at
all. Parameters are where preferences live (evening brightness, night setpoint, usual volume).

- **Table**: `smarthome_device_id` (resolved at write time, NULL if unknown; **no FK**, so
  history outlives a removed device and no longer blocks `DELETE /api/iot/devices/{id}`),
  `source`, `entity_ref` (HA entity_id / ST device id / ESPHome `host:key`), `command` (native),
  `requested_command` (the generic command asked for), `params` JSON, `success`, `message`,
  `origin` (`user` | `routine` | `system`), `user_id`, `context` JSON, `issued_at` (UTC, ms).
  730-day EVENT; added to `record_sa_storage_metrics_proc`.
- **One writer at the choke point**: `common/device_commands.record_device_command()` is called by
  the three low-level senders (`ha_control_device`, `st_control_device`,
  `control_esphome_device_async`) after every send, success or failure. Every caller is covered
  without remembering to log: all four API control endpoints (`origin="user"` + `user_id`),
  routines from the API's manual run and the daemon's schedule (`origin="routine"`, routine id in
  `context`), and audio casting (`origin="system"` by default). Best-effort: never raises.
- **Tests**: `tests/test_device_commands.py` plus an API attribution test. conftest's autouse
  `_no_device_command_db_writes` stubs the write in both `common` and `services.common` module
  objects, because on the NUC the pool's default `localhost:3306` is production.
- **Deployed**: backup `~/db_backups/alfr3d_backup_20261009_164715_pre_0049.sql.gz`, rehearsed on
  a restored copy (upgrade, downgrade, upgrade, plus a real insert that resolved
  `media_player.moonrise_tv` to device 60), migrated 0048 → 0049, rebuilt `service-api`,
  `service-daemon`, `service-device`. Not exercised with a live device command, to avoid
  changing a real device and writing a synthetic row into production; the first real command
  will be the live check.
