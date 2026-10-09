# LF-1b: Parquet bronze layer in `sa-learner`

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-1b

## Status: 🔲 Not started (planned 2026-10-09). Depends on LF-1a.

## Scope

- [ ] `sa_lake` named volume, mounted only on `sa-learner`. Layout
      `bronze/<table>/date=YYYY-MM-DD/*.parquet`, zstd.
- [ ] Pinned `duckdb` and `pyarrow` in `services/service_sa` requirements. No pandas or
      scikit-learn.
- [ ] Nightly incremental export per source table, by watermark (auto-increment id where one
      exists, otherwise the table's timestamp column), stored in a small watermark table. Sources:
      `device_history`, `household_events`, `card_interactions`, `attention_telemetry_history`,
      `device_location_history`, `smarthome_sensor_history`, `calendar_events`,
      `environment_history` and `device_command_history` (from LF-0), `listening_history`.
- [ ] Daily snapshots of current-state tables: `user`, `device`, `smarthome_devices`, `routines`,
      `environment`. These are how user types (resident vs. guest), device ownership and HA device
      churn are known historically.
- [ ] One-time backfill of everything currently in MySQL.
- [ ] Record bronze size alongside `sa_storage_metrics` so lake growth is tracked too.

## Verify

- Bronze row counts equal MySQL per table and date. A re-run adds nothing (watermark
  idempotency).
- Lake size after backfill, recorded here.
- `device_history` has no primary key (`migration_005_indexes.sql`): pick and document the
  watermark that makes its export idempotent.
