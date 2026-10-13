#!/bin/bash
# Daily MySQL backup with rotation (todo/todo_db_backup_cron.md).
#
# Dumps the alfr3d database from the running `mysql` compose service to a gzip file, verifies it,
# then keeps only the newest KEEP daily dumps. Credentials never leave the container: the root
# password and database name are read from the mysql container's own environment, so nothing is
# hardcoded here and .env is not touched. Rotation only ever touches `alfr3d_daily_*.sql.gz`;
# hand-made pre-migration dumps in the same folder are left alone.
#
# Env overrides: BACKUP_DIR (default ~/db_backups), KEEP (default 7), COMPOSE_DIR (repo root).
set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/db_backups}"
KEEP="${KEEP:-7}"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PREFIX="alfr3d_daily_"
MIN_BYTES=102400

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') db_backup_daily: $*"; }

mkdir -p "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.db_backup_daily.lock"
if ! flock -n 9; then
    log "another backup is already running, skipping"
    exit 0
fi

STAMP=$(date +"%Y%m%d_%H%M%S")
FINAL="$BACKUP_DIR/${PREFIX}${STAMP}.sql.gz"
PART="$FINAL.part"
trap 'rm -f "$PART"' EXIT

cd "$COMPOSE_DIR" || { log "FAILED: cannot cd to $COMPOSE_DIR"; exit 1; }

# pipefail makes a failing mysqldump fail the whole pipeline.
# --single-transaction: consistent InnoDB snapshot without locking tables.
# --routines/--events/--triggers: the SA retention EVENTs and the device_history triggers are part
# of the schema and must be in the dump.
if ! docker compose exec -T mysql sh -c \
    'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --events --triggers "$MYSQL_DATABASE"' \
    2>/dev/null | gzip -c > "$PART"; then
    log "FAILED: mysqldump exited non-zero"
    exit 1
fi

SIZE=$(stat -c %s "$PART")
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
    log "FAILED: dump is only $SIZE bytes"
    exit 1
fi
if ! gzip -t "$PART"; then
    log "FAILED: gzip integrity check failed"
    exit 1
fi
# mysqldump writes this trailer only when it ran to completion.
if ! gzip -dc "$PART" | tail -n 3 | grep -q "Dump completed"; then
    log "FAILED: dump has no completion trailer"
    exit 1
fi

mv "$PART" "$FINAL"
log "ok: $FINAL ($SIZE bytes)"

# Rotate: newest KEEP stay. Runs only after a verified-good dump, so a failing job never evicts
# good backups.
ls -1t "$BACKUP_DIR"/${PREFIX}*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f -- "$old" && log "rotated out: $old"
done
exit 0
