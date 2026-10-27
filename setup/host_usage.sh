#!/bin/bash
# Host-side usage snapshot for the disk_health card (todo/sa/todo_disk_and_lake_monitoring.md).
#
# Docker disk usage and ~/db_backups are invisible from inside the containers, so this runs from
# the host's crontab and writes a small tab-separated file that sa-learner reads through a
# read-only bind mount (docker-compose.yml: ./host_usage -> /host_usage). Read-only on the host
# too: it only runs `docker system df` and `du`; nothing is pruned or deleted.
#
# Env overrides: OUT_DIR (default <repo>/host_usage), BACKUP_DIR (default ~/db_backups).
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$REPO_DIR/host_usage}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/db_backups}"
OUT="$OUT_DIR/host_usage.tsv"

mkdir -p "$OUT_DIR"
TMP=$(mktemp "$OUT_DIR/.host_usage.XXXXXX")
trap 'rm -f "$TMP"' EXIT

DF=$(docker system df --format '{{.Type}}	{{.Size}}	{{.Reclaimable}}') || { echo "host_usage: docker system df failed" >&2; exit 1; }

{
    printf 'ts\t%s\n' "$(date +%s)"
    printf '%s\n' "$DF" | sed 's/^/docker\t/'
    COUNT=$(ls -1 "$BACKUP_DIR" 2>/dev/null | wc -l)
    BYTES=$(du -sb "$BACKUP_DIR" 2>/dev/null | cut -f1)
    printf 'backups\t%s\t%s\n' "$COUNT" "${BYTES:-0}"
} > "$TMP"

chmod 644 "$TMP"
mv "$TMP" "$OUT"
trap - EXIT
