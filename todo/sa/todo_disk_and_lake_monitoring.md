# Disk, lake and database growth monitoring + alert

> **Layer:** cross-cutting (data layer health) · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → not an LF phase; do before the lake or MySQL gets anywhere near the limit

## Status: 🟢 Done and deployed 2026-10-27. `disk.root` every 4 h, `check_disk_health` live, and host-side Docker + backup-folder usage (`setup/host_usage.sh`, host crontab `17 */4 * * *`, bind mount `./host_usage:/host_usage:ro`, `host.*` rows in `sa_storage_metrics`) verified on the NUC. 37.2 -> 42.3 GB free after pruning 4.7 GB of build cache.

## Why

Two decisions make SA storage grow without a ceiling, and nothing watches it:

- **The Parquet lake is deliberately uncapped** (2026-10-09, Athos): bronze keeps everything it
  has ever exported, so learners can see beyond MySQL's 730 days. At ~20 MB/month it is tiny
  today (23 MB for 3.8 M rows), but the household can add devices, sensors and Kit customers.
- **MySQL keeps 730 days of every SA variable** (LF-0). `device_history` alone grows to roughly
  4-5 GB.

And the host has already surprised us once: free space fell from **37 GB (09-13) to 25 GB
(10-09)** with no SA table responsible. The cause was Docker build cache (7.8 GB reclaimable),
unused images (5.6 GB) and uncompressed SQL backups (2.8 GB), found by hand. A cleanup on
2026-10-09 got it back to 36 GB. The next time, there should be a card before it is a problem.

## What to watch

| Signal | Source | Notes |
|---|---|---|
| Host disk free (% and GB) | `os.statvfs('/lake')` inside `sa-learner` | Docker named volumes live on the host root filesystem, so this reports the real disk (verified 2026-10-09: 38.5 GB free of 117 GB, matching `df /`). No new mount needed. |
| Lake size and growth, per table | `sa_storage_metrics` rows `lake.<table>`, already written nightly by `lake.record_lake_sizes()` | Growth rate = slope over the last 30 days. |
| MySQL table sizes and growth | `sa_storage_metrics`, written daily by `record_sa_storage_metrics_event` | Already has `device_history`, `smarthome_sensor_history`, etc. |
| Docker reclaimable space | `docker system df` | Not visible from a container; either mount the socket read-only (the API already has it) or approximate from host disk trend. |
| Backup folder size | `~/db_backups` is on the host, outside Docker | Needs a host-side check or a bind mount; backups were the single biggest avoidable item. |
| Days until full | free space ÷ recent daily growth of total disk use | The number to alert on, since a slow leak and a sudden jump need different thresholds. |

## Alert design

Reuse what exists rather than a new channel:

- **An SA card**, following `check_system_health` in `service_sa/sa/engine.py`: sets `urgent`
  (never suppressed, no dismiss) and is debounced so one noisy reading can't raise it. A new
  `check_disk_health` rule, reading the latest `disk.root` row, no new query pattern.
- **Spoken/Deck notification** only at the critical tier.
- **Thresholds (proposal, tune after a month of data):**
  - *warn*: free < 20 % **or** < 15 GB **or** days-until-full < 60 → ambient card
  - *critical*: free < 10 % **or** < 7 GB **or** days-until-full < 14 → urgent card + speak
  - *lake*: lake growth > 5x its trailing 30-day average in a week (a runaway exporter), or
    lake > 25 % of free space → warn
- Each card says what is big and what is safe to prune (build cache, old backups, logs), but
  never deletes anything itself.

## Work items

- [x] Add a `disk.root` sample (free bytes, total bytes) to `sa_storage_metrics` from
      `sa-learner`, every 4 h from `sa-learner` (`learner.record_disk_sample`; `row_count` = total bytes, `data_bytes` = free bytes). No migration: same table, new `table_name`.
- [x] Days-until-full estimate from the last 30 days of samples, with a floor on history so a
      fresh install doesn't alert from two points.
- [x] `check_disk_health(frame)` rule with the warn/critical tiers above; `because` lists the
      current free space, the 30-day growth and the three biggest consumers.
- [x] Docker usage and `~/db_backups`: host cron writes a TSV the learner reads through a read-only bind mount (chosen over a socket mount; 2026-10-27, PR #328).
- [x] **Automatic backup rotation** (done 2026-10-13, tracked in [../todo_db_backup_cron.md](../todo_db_backup_cron.md): daily dump, keep 7): keep the N newest in
      `~/db_backups`, compress on write (`.sql.gz` is ~16x smaller). Today it is a manual step in
      the migration routine.
- [x] Tests: threshold tiers, debounce, no alert on thin history (`tests/test_sa_disk.py`). Debounce = two consecutive samples must agree.
- [x] Document the prune commands that are safe on this host (README, "Disk hygiene", 2026-10-27).

## Open questions

- Is a lake size cap ever wanted? Currently **no** (decided 2026-10-09). If the Kit ships on
  smaller disks (the Pi 5 BOM in Notion) this needs revisiting, and the alert thresholds should
  scale with disk size, not be absolute GB.
- Who gets the critical alert if nobody is home? The existing card/speak path assumes someone is.
