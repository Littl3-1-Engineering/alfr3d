# LF-8: Context registry and capture ledger (Timeline "Context learning 2/5")

Layer: data and tooling | Roadmap: [SA_ROADMAP.md](SA_ROADMAP.md) | Depends on: LF-2b

Status 2026-11-19: **built and proven on a copy of the production lake; not merged or deployed.**
Branch `feat/sa-context-registry`. Everything here is lake-side or code; no MySQL schema change was
made or is needed for the registry, the gold tables, the identity fix or the ledger script.

## What exists

- **`sa/context_registry.py`.** Every context feature is declared once as a `Feature` (key, kind,
  an SQL `value` expression over named joins, grain, lags, coverage floor, provenance, source
  retention, privacy scope, readers). Everything downstream is generated from the declaration:
  gold `context_features` (long form: `feature_key, bucket_utc, value_num, value_text`), gold
  `context_hourly` (a pivot of it, the table every learner is meant to join to), the ledger, and
  `learner_candidates()`. A new signal is one `Feature(...)` (a new source *table* is one `JOINS`
  entry as well); no SQL elsewhere, no learner code. Series families already long-form in
  `scalar_hourly` (ESPHome, Home Assistant, Deck battery, attention) are registered as
  `SeriesFamily` so the ledger and the privacy rules cover them.
- **`silver_contexts.build_gold`** now generates `context_features` and `context_hourly` from the
  registry instead of a hand-written query; `silver.build` writes `context_features` first and
  re-registers the gold views so `context_hourly` can pivot it.
- **`sa/identity.py`.** The one naming rule silver already used (an ESPHome sensor is `host:name`,
  other sources `source:ha id | st id | name`) in Python, plus `history_ids` / `esphome_climate_ids`
  returning EVERY `smarthome_devices` id a sensor has ever had (current rows plus
  `sa_sensor_aliases`). `shadow.climate` (live) now queries the sensor's history by that set
  (`smarthome_device_id IN (...)`, parameterised) instead of one row id.
- **`sa/ledger.py`** (`python -m sa.ledger [--window-days 30]`, read-only): per feature and per
  series, capture status, first and last bucket, rows, hours with data and coverage over the last
  30 days, source retention, readers, provenance, identity rule, and a `note`. A series whose
  prefix is not registered is listed under `unregistered`.
- **Privacy scope** is enforced in code: `restricted` features (`precise_location`, registered but
  never captured) are never built into `context_features` (`buildable()`), never returned by
  `learner_candidates()` even if a caller names them, and `validate()` rejects a restricted
  feature that has an expression or a `context_hourly` column. `owner_opened` ones are exposed only
  when named by the owner.

## Acceptance (the prompt's list) and the evidence

| criterion | result |
|---|---|
| a throwaway feature needs one registration and no learner or SQL edit | test: `p.people_home * 2.0` registered once reaches `context_features` and `context_hourly` (existing columns do not move; it can also be kept out of the wide table) |
| `context_hourly` output unchanged, proven by a diff test on real data | **Real data:** a copy of the production lake rebuilt with the new code against production's own `context_hourly` (built by the old code): same columns in the same order, **5,265 rows, 0 only in old, 0 only in new**; the other 8 gold tables also identical (`EXCEPT` both ways). Three column *types* changed with identical values: `outdoor_humidity_pct` and `outdoor_pressure_hpa` BIGINT to DOUBLE (more general; the source happened to be integral), `people_home` kept DOUBLE. **Synthetic:** the original hand-written SQL is kept verbatim in `tests/test_sa_context_registry.py` and diffed against the generated one in all four combinations of optional sources |
| ledger matches the Phase 0 inventory | on the same copy: weather starts 2026-10-09 20:00 (Phase 0: `environment_history` from 10-09 20:26), 944 hourly rows, 99.9 % of the last 30 days; ESPHome series earliest 2026-09-16 15:00 (Phase 0: 09-16 15:22), mean 30-day coverage 0.983; Deck series earliest 2026-10-11 11:00 (Phase 0: 10-11 11:40), 0.698; attention from 2026-08-30, 0.933; Home Assistant from 2026-09-30, 31 series, 0.874; `unregistered` empty |
| CI green | pending on the PR; 766 SA tests pass locally |

## The ESPHome orphan finding, reproduced and fixed

Phase 0 could not power-cycle a production sensor, so it was reproduced from history. The node's
temperature readings sit under id **37885** (2026-09-16 15:22 to 09-27 02:31, 144,219 rows) and
then under **37893** (09-27 02:40 to now, 793,144 rows); humidity likewise 37889 then 37897. The
nine-minute gap is the power cycle. Silver was already immune (identity view plus aliases), but
`shadow.climate` queried one row id, so right after a power cycle its look-back would have been
empty and `climate_deviation` blind until a fresh window accumulated. It now reads the sensor's
history by stable key across both ids (SQL validated against the production database, read-only:
`current 37893, aliased 37885`; `current 37897, aliased 37889`). No migration: `sa_sensor_aliases`
already exists. The aliases are still a human decision (a new power cycle needs a new alias row for
the lake side); proposal 2 below removes that.

## Findings

- **No learner reads `context_hourly` today.** The wide table has been built nightly for weeks and
  nothing joins to it. `scalar_baseline` reads weather straight from silver `weather_hourly`
  (`COVARIATE_SERIES = "weather:temperature_c"`). The registry is the thing that makes the table
  worth reading; Phase 3's shared covariate engine is its first consumer.
- **`calendar_busy_minutes` is zero-filled.** The original `COALESCE(c.busy_minutes, 0)` means the
  ledger shows it "captured since 2026-04-12, 99.9 % coverage", but the calendar was first captured
  on 2026-10-09 (the MySQL table keeps 730 days since LF-0; an earlier version of this note and the
  registry wrongly said it was purged after each event): every hour before that reads 0 ("free") when the truth is "unknown". Pre-existing,
  kept as is so `context_hourly` is unchanged, and flagged in the ledger `note`. This is the kind of
  fabricated-looking value the "no fabricated data" rule is about; see proposal 1.

## Needs your decision (nothing below is built)

1. **Calendar zero-fill.** Make `calendar_busy_minutes` NULL for hours before the first calendar
   bronze day (and for any hour the calendar export did not run), 0 only where it was captured.
   Changes `context_hourly` values for about 4,300 hours (2026-04-12 to 10-08) from 0 to NULL; no
   reader today, so no behaviour changes. One line in the registry plus a test.
2. **Alias maintenance.** Derive `sa_sensor_aliases` automatically (a retired id whose
   `esp_entity_id` host and name match a live row) instead of by hand, so a power cycle never needs
   a human step. Writes to an existing MySQL table; no schema change.
3. **Ledger API route, needs migration 0063.** The API does not mount the lake (only `sa-learner`
   does), so a route needs the ledger in MySQL. Plan: new table `sa_context_ledger` (`key` VARCHAR
   (96) PK, `kind`, `status`, `capture_start`, `last_seen`, `rows`, `hours_30d`, `coverage_30d`,
   `retention_days`, `privacy`, `readers` JSON, `provenance`, `note`, `computed_at`), written by
   `sa-learner` after each silver build (replace-all, small: about 60 rows), read by a new
   `GET /api/context/ledger` in `service_api/routes/context.py`, read-only, GET so no RBAC write
   gate. Before running it on production: a real `mysqldump` of the production database, trailer
   verified, as for 0062 (`~/db_backups/..._pre_0063.sql.gz`); rollback is `alembic downgrade 0062`
   (drops the one table) or restoring the dump; migration round-tripped 0062 to 0063 to 0062 on a
   throwaway MySQL 8 first. **I have not written the migration.** The script already answers the
   question; the route is only for the web UI and the Deck.
4. **Deploy.** Merging changes nothing live until deployed. On deploy the next nightly build writes
   `context_features` and the registry-generated `context_hourly`, and `shadow.climate` starts using
   stable ids at once. Re-run the real-data diff against the then-current production table after the
   first nightly as the final check.
