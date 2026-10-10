# LF-1b: Parquet bronze layer in `sa-learner`

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-1b

## Status: 🟢 Deployed to the production NUC 2026-10-09/10. Backfill done; the scheduled nightly run (03:30 UTC) has since fired on its own (2026-10-10).

3.8 M rows across 10 event tables plus 7 daily snapshots are in the lake: **23 MB** on disk
(`device_history` alone: 2,998,061 rows, 13.1 MB in Parquet vs. 628 MB in MySQL).

## Scope

- [x] `sa_lake` named volume, mounted only on `sa-learner`. Layout
      `bronze/<table>/date=YYYY-MM-DD/*.parquet`, zstd.
- [x] Pinned `duckdb` and `pyarrow` in `services/service_sa` requirements. No pandas or
      scikit-learn.
- [x] Nightly incremental export per source table, by watermark (auto-increment id where one
      exists, otherwise the table's timestamp column), stored in a small watermark table. Sources:
      `device_history`, `household_events`, `card_interactions`, `attention_telemetry_history`,
      `device_location_history`, `smarthome_sensor_history`, `calendar_events`,
      `environment_history` and `device_command_history` (from LF-0), `listening_history`.
- [x] Daily snapshots of current-state tables: `user`, `device`, `smarthome_devices`, `routines`,
      `environment`. These are how user types (resident vs. guest), device ownership and HA device
      churn are known historically.
- [x] One-time backfill of everything currently in MySQL.
- [x] Record bronze size alongside `sa_storage_metrics` so lake growth is tracked too.

## Verify

- [x] Row counts equal MySQL **per table and per day** for every past day (`python -m sa.lake
      verify`; today is excluded because rows keep arriving). Passed after the backfill and again
      after a re-run.
- [x] Re-run adds nothing: it rewrote only the last two days (32,751 `device_history` rows) and
      verify still passed.
- [x] Lake size after backfill: 23 MB (see above).
- [x] `device_history` has no primary key; its cursor is `timestamp`, which the trigger sets to
      `NOW()` at insert (`createTables.sql`), so rows arrive in order and a 1-day lookback is
      enough. It is indexed, so the ordered scan is cheap.
- [x] DuckDB reads the Hive layout directly (`read_parquet(..., hive_partitioning=true)`).
- [x] The scheduled 03:30 UTC run fired on its own on 2026-10-10: `bronze export done, failures: none` at 03:30:15. Check
      `docker logs alfr3d-sa-learner-1` for `bronze export done` after tonight.

## What actually happened

- **No new MySQL state.** The plan called for a watermark table. It turned out to be unnecessary:
  the resume point is derived from the partitions already on disk (newest `date=` minus a one-day
  lookback, capped at today so a future-dated calendar event can't push it past unexported days).
  So no migration, and the lake can be rebuilt by deleting a table's folder and re-running.
- **Day partitions are rewritten whole**, in a temp dir swapped in with `os.replace`, so a crash
  can't leave a half-written partition. That, not row-level watermarks, is what makes a run
  idempotent.
- **Secrets stay out.** Excluded by name: `user.password_hash/email/about_me`, `device.stream_url`
  (camera URLs embed credentials), `smarthome_devices.last_state` (HA attributes carry signed
  `entity_picture` tokens), `routines.actions` (email recipients/bodies). A regex backstop refuses
  to export any column that looks like a secret, so a future `api_token` column fails loudly. The
  lake still holds household PII that already lives in MySQL (location fixes, message text in
  `household_events`); it lives on a Docker volume, not in the repo.
- **Bronze is not subject to the 730-day cap, by decision (Athos, 2026-10-09).** MySQL deletes at
  730 days; the lake keeps everything it has exported, at roughly 20 MB per month, so learners
  can see more than two years later. Growth monitoring and a low-disk alert are tracked in
  [todo_disk_and_lake_monitoring.md](todo_disk_and_lake_monitoring.md).
- **One lock, one process at a time.** A manual backfill and the nightly job can't interleave
  (`.export.lock`, non-blocking). The nightly job touches the learner's heartbeat per day written,
  because the watchdog kills the process when it goes stale and a first run is a multi-minute
  backfill. The manual backfill ran as a separate `docker exec` process (2m45s) so the learner's
  loop was never held.
- **`sa_lake` is root-vs-uid-1000 safe**: `/lake` is created and chowned in the image, so the
  named volume comes up owned by uid 1000.
- **Lake sizes are tracked** in `sa_storage_metrics` as `lake.<table>` rows (no new table).

## Known limits / follow-ups

- `smarthome_sensor_history`, `household_events` and `card_interactions` have no index starting
  with their time column, so each nightly run scans and sorts the whole table. Fine now (758k rows
  in ~19 s), but sensor history grows ~60k rows/day; add `(recorded_at)` indexes via a migration
  before it reaches the tens of millions.
- A row inserted more than one day behind the newest partition is missed until a full backfill
  (delete the table's folder and re-run). Only relevant for `household_events`, whose timestamp
  comes from the producer.
- Small tables get one tiny file per day. Compaction can wait until file counts matter.
- `pymysql` prints `db`/`passwd` deprecation warnings (same as the rest of the codebase).
