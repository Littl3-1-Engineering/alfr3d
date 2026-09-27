#!/bin/bash
# Self-service update sequence (todo/todo_selfservice_release_update.md). Runs once, inside an
# ephemeral container spawned by service-api, then exits. Deliberately not `set -e`: every step
# that can fail is checked explicitly so the right status/cleanup happens on each failure path
# rather than the script just dying mid-sequence.
set -uo pipefail

STATUS_DIR=/status
STATUS_FILE="$STATUS_DIR/update_status.json"
LOCK_FILE="$STATUS_DIR/update.lock"
# Bind-mounted at the same absolute path inside this container as on the host (not a fixed
# /repo) -- docker compose, invoked from here but talking to the *host's* daemon over the
# bind-mounted socket, resolves docker-compose.yml's own relative bind mounts (./nginx.conf,
# ./certs, ...) against this cwd, and that resolved path is handed straight to the host daemon.
# A container-local path like /repo would be meaningless there; identical paths on both sides
# sidesteps the translation entirely (confirmed necessary via a real dry-run failure).
REPO_DIR="${HOST_REPO_PATH:?HOST_REPO_PATH env var is required}"
LOG_FILE="$(mktemp /tmp/update_log.XXXXXX)"

TARGET_TAG="${TARGET_TAG:?TARGET_TAG env var is required}"
BACKUP_FILE="${BACKUP_FILE:-}"
HEALTHCHECK_TIMEOUT_SECONDS="${HEALTHCHECK_TIMEOUT_SECONDS:-360}"
HEALTHCHECK_POLL_INTERVAL_SECONDS=5

cd "$REPO_DIR" || {
  echo "Cannot cd to $REPO_DIR" >&2
  exit 1
}

# The bind-mounted repo is owned by the host user, not whatever UID this container runs as --
# git's dubious-ownership check refuses to operate on it otherwise (confirmed via a real
# dry-run: "fatal: detected dubious ownership in repository at '/repo'", then again at
# '/repo/.git' from a different internal git codepath). Wildcarded rather than just $REPO_DIR
# since this container only ever touches this one bind-mounted repo, for this one purpose --
# no other repo's trust is at stake.
git config --global --add safe.directory '*'

# Refuse a second concurrent run rather than two updates racing each other's git checkout/build.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another update is already running" >&2
  exit 1
fi

write_status() {
  local state="$1" phase="$2" message="${3:-}"
  local tmp
  tmp="$(mktemp "$STATUS_DIR/.status.XXXXXX")"
  jq -n \
    --arg state "$state" \
    --arg phase "$phase" \
    --arg tag "$TARGET_TAG" \
    --arg message "$message" \
    --arg backup_file "$BACKUP_FILE" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{state: $state, phase: $phase, target_tag: $tag, message: $message, backup_file: $backup_file, updated_at: $ts}' \
    >"$tmp"
  mv "$tmp" "$STATUS_FILE"
}

log_tail() {
  tail -n 50 "$LOG_FILE" 2>/dev/null
}

# Every build-based service (excludes zookeeper/kafka/redis/mysql/nginx, which are pulled base
# images this mechanism doesn't rebuild or roll back -- a release that also bumps one of those
# pinned base-image tags is outside this rollback mechanism's coverage, same as the migrate
# service's "test" profile name: a documented, deliberate scope boundary, not an oversight.
PROJECT_NAME="$(docker compose config --format json | jq -r '.name')"
BUILD_SERVICES="$(docker compose config --format json | jq -r '.services | to_entries[] | select(.value.build) | .key')"

pre_tag_images() {
  for svc in $BUILD_SERVICES; do
    docker tag "${PROJECT_NAME}-${svc}:latest" "${PROJECT_NAME}-${svc}:pre-update" 2>>"$LOG_FILE"
  done
}

rollback_images() {
  for svc in $BUILD_SERVICES; do
    docker tag "${PROJECT_NAME}-${svc}:pre-update" "${PROJECT_NAME}-${svc}:latest" 2>>"$LOG_FILE"
  done
}

# All-healthy -> 0; any-unhealthy -> 1; still-starting past the timeout -> 2. Never conflates
# "waiting" with "actually healthy" or "actually broken", since the two failure branches above
# lead to very different next steps (rollback vs "we don't know, alert loudly").
wait_for_healthy() {
  local elapsed=0
  while [ "$elapsed" -lt "$HEALTHCHECK_TIMEOUT_SECONDS" ]; do
    local statuses
    statuses="$(docker ps --filter "label=com.docker.compose.project=${PROJECT_NAME}" --format '{{.Status}}')"
    if echo "$statuses" | grep -q '(unhealthy)'; then
      return 1
    fi
    local total unhealthy_or_starting
    total="$(echo "$statuses" | grep -c .)"
    unhealthy_or_starting="$(echo "$statuses" | grep -vc '(healthy)')"
    if [ "$total" -gt 0 ] && [ "$unhealthy_or_starting" -eq 0 ]; then
      return 0
    fi
    sleep "$HEALTHCHECK_POLL_INTERVAL_SECONDS"
    elapsed=$((elapsed + HEALTHCHECK_POLL_INTERVAL_SECONDS))
  done
  return 2
}

write_status running fetch "Fetching ${TARGET_TAG}"
PREV_SHA="$(git rev-parse HEAD)"

if ! git fetch --tags origin >>"$LOG_FILE" 2>&1; then
  write_status failed fetch "git fetch failed: $(log_tail)"
  exit 1
fi

# Deliberately detached HEAD: the working tree must match exactly what the release notes
# described, not whatever main has drifted to since. A bare `git pull` on this detached HEAD
# will confusingly no-op/error later -- that is expected, not a bug, if a human ever SSHes in.
if ! git checkout "tags/${TARGET_TAG}" >>"$LOG_FILE" 2>&1; then
  write_status failed fetch "tag ${TARGET_TAG} not found: $(log_tail)"
  exit 1
fi

pre_tag_images

write_status running build "Building images for ${TARGET_TAG}"
# --profile test --profile tools: a bare `docker compose build` silently skips profile-gated
# services. Without naming both profiles here, `migrate` would run against a stale image on any
# release with new migrations, and service-updater would never rebuild itself for the next one.
if ! docker compose --profile test --profile tools build >>"$LOG_FILE" 2>&1; then
  write_status failed build "build failed, no containers touched: $(log_tail)"
  git checkout "$PREV_SHA" >>"$LOG_FILE" 2>&1
  exit 1
fi

write_status running migrate "Applying database migrations"
if ! docker compose --profile test run --rm migrate >>"$LOG_FILE" 2>&1; then
  write_status failed migrate "migration failed, previous containers still running old code/schema: $(log_tail)"
  git checkout "$PREV_SHA" >>"$LOG_FILE" 2>&1
  exit 1
fi

write_status running recreate "Recreating containers"
if ! docker compose up -d >>"$LOG_FILE" 2>&1; then
  write_status running rollback "Recreate failed to even start, rolling back containers: $(log_tail)"
  rollback_images
  docker compose up -d >>"$LOG_FILE" 2>&1
  if wait_for_healthy; then
    write_status rolled_back rollback "Rolled back to the previous version after a failed recreate. Schema is still at the new migration head -- restore ${BACKUP_FILE:-the pre-update backup} if the previous version can't run against it."
  else
    write_status failed rollback "Rollback recreate also failed to go healthy -- manual intervention needed: $(log_tail)"
  fi
  exit 1
fi

write_status running healthcheck "Waiting for every service to report healthy"
wait_for_healthy
healthcheck_result=$?

if [ "$healthcheck_result" -eq 0 ]; then
  write_status success done "Updated to ${TARGET_TAG}"
  exit 0
fi

# healthcheck_result is 1 (a container reported unhealthy) or 2 (timed out still starting) --
# both go through the same automatic container rollback. The database is never auto-restored
# here: migrate already succeeded, so the schema is ahead of the code being rolled back to, and
# guessing that a container-health failure means the schema is the problem would risk discarding
# writes made during the update window for no good reason.
write_status running rollback "New containers did not become healthy, rolling back images"
rollback_images
if ! docker compose up -d >>"$LOG_FILE" 2>&1; then
  write_status failed rollback "Rollback recreate command itself failed: $(log_tail)"
  exit 1
fi

if wait_for_healthy; then
  write_status rolled_back rollback "Rolled back to the previous version. Schema is still at the new migration head -- restore ${BACKUP_FILE:-the pre-update backup} if the previous version can't run against it."
else
  write_status failed rollback "Rollback recreate did not go healthy either -- manual intervention needed: $(log_tail)"
fi
exit 1
