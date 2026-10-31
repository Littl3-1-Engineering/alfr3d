#!/bin/bash
# Re-check the nginx leaf cert on demand (todo/todo_on_demand_containers.md).
#
# service-tls is a run-once container: `docker compose up -d` runs it as nginx's dependency (so it
# also runs at boot via alfr3d.service), and this script is the other two triggers -- the daily
# crontab entry and a manual run after moving the box to a new network:
#
#   30 4 * * * /home/alfr3d/alfr3d/setup/tls_reissue.sh >> /home/alfr3d/db_backups/tls.log 2>&1
#
# It re-issues the leaf only if the host's addresses changed or it is <30 days from expiry, and
# service-tls itself HUPs nginx when it does. The CA key (tls_ca volume) is never touched. Must go
# through `docker compose run`, not write ./certs directly: server.key is root:root 0600.
#
# Env overrides: COMPOSE_DIR (default: repo root).
set -uo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') tls_reissue: $*"; }

cd "$COMPOSE_DIR" || { log "FAILED: cannot cd to $COMPOSE_DIR"; exit 1; }

# Same lock idea as db_backup_daily.sh; kept next to the compose file so cron and a manual run
# can't overlap, and an updater-driven `up -d` that also runs service-tls is the only other writer.
exec 9>"$COMPOSE_DIR/certs/.tls_reissue.lock"
if ! flock -n 9; then
    log "another run is already in progress, skipping"
    exit 0
fi

# --no-deps: run only this service, don't start nginx/anything else. --rm: no stray exited
# `service-tls-run-*` containers. -T: no TTY under cron.
if docker compose run --rm --no-deps -T service-tls; then
    log "ok"
else
    rc=$?
    log "FAILED: service-tls exited $rc (nginx keeps serving whatever leaf is on disk)"
    exit "$rc"
fi
