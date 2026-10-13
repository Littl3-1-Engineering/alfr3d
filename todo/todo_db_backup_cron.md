# Daily database backup with 7-day rotation

## Status: 🟢 Built, tested and installed on the NUC 2026-10-13 (`setup/db_backup_daily.sh`, user crontab `0 4 * * *`). First scheduled run is 2026-10-14 04:00 local. Off-box copy and failure alerting remain open.

## Why

Backups are taken by hand before each migration (`mysqldump` into `~/db_backups` on the NUC) and
never pruned. Uncompressed SQL backups were part of the 2026-10-09 disk surprise (2.8 GB), see
[sa/todo_disk_and_lake_monitoring.md](sa/todo_disk_and_lake_monitoring.md). The manual
pre-migration dump stays; this adds an unattended daily one so a bad day never costs more than 24 h.

## Requirements

- Runs **daily** (propose ~04:00 local, after the 03:30 UTC lake export has finished) from the
  host's cron or a systemd timer. The NUC already uses systemd for compose, so a timer is the
  natural fit; cron is fine if simpler.
- Takes a consistent dump: `mysqldump --single-transaction --routines --events --triggers`
  (the SA retention EVENTs and `device_history` triggers must be in the dump), piped through `gzip`
  to `~/db_backups/alfr3d_daily_YYYYmmdd_HHMMSS.sql.gz`. Compressed is ~16x smaller.
- **Keeps the last 7** daily backups and deletes older ones. Rotation touches only files matching
  `alfr3d_daily_*.sql.gz`, never the hand-made pre-migration dumps (`*_pre_*.sql[.gz]`).
- Writes the dump to a temp name and renames it on success; a failed or empty dump must not count
  towards the 7 or evict a good one. Rotation runs only after a verified-good dump (non-zero size,
  `gzip -t` passes).
- Reads credentials from the environment/`.env` without modifying it; no secrets in the script or
  the repo. Never re-initialises the database container.
- Logs one line per run, and a failure is visible: exit non-zero so systemd marks the unit failed,
  and surface it (ideally as an SA card via the `disk_health`/`system_health` pattern, or at least
  in the journal).

## Work items

- [x] Script in `setup/` (e.g. `setup/db_backup.sh`) doing dump, verify, rename, rotate.
- [x] Cron entry (user crontab, not systemd: no sudo needed) installed; documented in the README maintenance section. Original item: systemd service + timer (or crontab line) installed by the existing setup path; document it
      in the README operations section.
- [x] Tested with a scratch backup dir: rotation keeps exactly N, leaves `*_pre_*` alone, a failing dump (fake `docker`) exits 1, evicts nothing and leaves no `.part`. Original item: test the script off-NUC against the test MySQL (port 3307): rotation keeps exactly 7, leaves
      `*_pre_*` files alone, a failed dump evicts nothing.
- [x] Real restore of a produced dump into an ephemeral `test-mysql` database: user/device/household_events/device_history/sa_storage_metrics counts match live (live slightly ahead), 14 events and the trigger present. Original item: do a real restore from one of the produced files into a scratch database to prove it works.
- [ ] Decide on an off-box copy (the NUC's disk is the single point of failure); out of scope for
      the first version.
- [ ] (open) Mark the "Automatic backup rotation" item in the disk-monitoring doc done, and let
      `check_disk_health` report the backup folder size once this exists.

## Still open

- **Failure is only visible in `~/db_backups/backup.log`** (cron has no mail here). Add a staleness
  check: `check_disk_health` (or a sibling rule) should warn when the newest `alfr3d_daily_*` is over
  ~36 h old. That needs the backup folder visible to the SA containers (read-only mount), the same
  gap as the backup-folder-size item in the disk monitoring doc.
- The 7 dailies are ~26 MB each (about 185 MB), so the disk cost is small.
