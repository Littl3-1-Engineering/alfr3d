# Todo: SSH-free release update (GitHub release check + "Update Now" banner)

## Status: 🟡 Built and released in v0.4.9 "Room Service" (2026-09-27): all three phases, off-NUC dry run
passed. **Still owed (checked 2026-10-04):** Testing plan step 3 -- the first real update pushed
through the mechanism on the production NUC. It cannot happen until a release newer than the NUC
exists: the NUC is on `main` (`v0.4.9-6-g82a70b67`, branch checkout, not a tag), `update-check`
correctly reports up-to-date, and the status volume is empty. Also open: the "settles within 360 s
under normal single-stack load" timing, which the scratch dry run could not confirm (resource
contention from two stacks on one host). Plan: cut the next patch release, then use **Update Now**
on the NUC as the real test -- after which the NUC will sit on a detached tag HEAD (see the
detached-HEAD note below; `git pull` there no-ops).

_The plan text below is the original 2026-09-27 design and is kept for the architecture reasoning;
its "No code yet" / "next session" phrasing is historical._

## Problem

Today, shipping a new `alfr3d` release to the household's NUC means SSHing in and running
`git pull` + `docker compose build` + `docker compose up -d` by hand (v2 only — see
`todo_compose_container_name_collision.md` for what mixing v1/v2 here already broke once), plus,
for releases that touch schema, manually invoking the `migrate` one-shot container too (see
finding below — this is currently undocumented/manual and almost got missed by this plan).
That's fine for Athos, but it means nobody else in the household — and no future non-technical
user of a packaged "ALFR3D Kit" — can ever update the box themselves.

Goal: detect that a newer GitHub release exists, surface it as a banner/notification in the web
frontend, and let an authorized user click **Update Now** and have the update happen without
touching a terminal.

## What's already there (confirmed by reading the code, 2026-09-27)

- **`services/VERSION`** is the single source of truth for the running version
  (`services/service_api/routes/health.py`) — currently `0.4.8`. Releases are tagged on GitHub
  (`Littl3-1-Engineering/alfr3d`, `v0.1.0`…`v0.4.8`, most with a release title like "v0.4.8:
  Vital Signs").
- **`service-api` already has `docker.sock` mounted and runs `privileged: true`.** It already
  shells out to `docker ps` / `docker inspect` / `docker stats` / `docker restart` for the
  container-health panel and the existing per-service **Restart** button
  (`routes/containers.py`, `routes/system.py:restart_service`). The plumbing for "backend
  container triggers a docker operation" is proven and in production. Note: `run_docker_command`
  hard-codes a 10s `subprocess.run` timeout — fine for `docker ps`/`restart`, useless for anything
  update-related; the new code needs its own long-running-command path, not a reuse of that
  helper.
- **RBAC already has a home for this.** `auth/permissions.py` gates the whole `"system"` scope
  (wildcard) as owner/technoking-only. `restart_service` and `database/backup` already use
  `Depends(require_permission("system", "..."))`. An update action slots into this same scope
  with no new role model needed — reuse `require_permission("system", "update")`.
- **Frontend already has the right home.** `services/service_frontend/src/components/System.jsx`
  is the existing admin panel (network info, DB info, config editor, per-service restart), gated
  on `isAuthenticated`, polling `/api/system/*` and `/api/containers`. This is where a "Version:
  0.4.8 (up to date / v0.4.9 available)" row belongs. A separate top-of-app banner is needed too,
  since System.jsx is a collapsible panel a user may never open.
- **A WebSocket broadcast channel pattern already exists** (`manager.broadcast("containers",
  ...)`) that the frontend already consumes — the natural way to push "update available" and
  progress to an open browser tab without every tab polling.

## New finding while scoping this: migrations are also a manual, undocumented step today

`docker-compose.yml` has a `migrate` service (`profiles: ["test"]`, `CMD ["alembic", "upgrade",
"head"]`, built from `setup/migrations/Dockerfile`) that applies the real alembic chain in
`setup/migrations/versions/`. It is **not** run by a plain `docker compose up -d` — it's gated
behind a profile literally named `"test"`, despite applying migrations against the real
`MYSQL_DATABASE`/`MYSQL_NAME` env vars (i.e. production), which only run when someone explicitly
does `docker compose --profile test run --rm migrate`. Past releases that needed a schema change
(memory: "migrated (0026→0035)", "alembic 0037") applied this by hand over SSH, same as
everything else. **This has to be step 4.5 in the update sequence below, or an SSH-free update
mechanism just silently ships app code against a stale schema on the next migration-bearing
release.** (The `"test"` profile name on a service that's also used for real prod migrations is
its own small naming oddity — not fixing that here, just documenting the exact command needed:
`docker compose --profile test run --rm migrate`.)

## Why this is harder than "hit the GitHub API and call `git pull`"

1. **Images are built from source, not pulled from a registry.** `docker-compose.yml`'s services
   all use `build: context: ./services/...`. There is no `docker pull` shortcut — an update is
   `git pull` + `docker compose build` (rebuilds every changed image, several minutes) + migrate
   + `docker compose up -d` (recreates containers). This has to run as a background job with a
   status the frontend can poll/subscribe to, never as a synchronous request — it will outlive
   any reasonable HTTP timeout.
2. **`service-api`'s own repo mount is read-only** (`.:/project:ro` in `docker-compose.yml`).
   It can't `git pull` into itself as-is, and — separately — deliberately widening the most
   privileged, already-`privileged: true`/docker.sock-holding container to also have read-write
   access to its own source tree is a bigger blast-radius increase than it looks.
3. **`service-api` can rebuild itself out from under the request that triggered the rebuild.**
   If service-api's own image is one of the ones being rebuilt/recreated, the process handling
   the "start update" request may get killed mid-update by its own action.
4. **A failed build must not touch what's currently running.** `docker compose build` failing
   partway through (bad tag, network blip, disk full) has to abort *before* migrate/`up -d` — the
   existing production containers must be left alone. Precedent: the compose v1/v2 mixup already
   caused a real outage + stranded containers once (`todo_compose_container_name_collision.md`);
   this feature must not become a second way to hit the same class of failure.
5. **This is a meaningfully privileged remote action.** Today, a human SSHing in to update
   implicitly reads the diff/release notes before running anything. Automating "click a button,
   host executes `docker compose build` against whatever the git remote currently has" removes
   that human checkpoint unless the UI preserves it.
6. **Concurrency.** Two overlapping update runs (two tabs, or a double-click) must not both try
   to `git pull`/build at once — needs a lock.

## Architecture options for *where the update actually executes*

This is the one real design decision in this whole feature — everything else (banner, version
row, GitHub polling) is straightforward. Three options, evaluated in detail:

### Option 1 — Ephemeral one-shot "updater" container, spawned by `service-api` via its existing docker.sock

`service-api` runs `docker run -d --rm` for a short-lived helper container (from a small,
dedicated `alfr3d-service-updater` image, not service-api's own image) that gets the repo bind
mount **read-write** and its own docker.sock access, runs the whole update sequence, writes
progress/result to a shared status file on a named volume, and exits/self-removes.

- **Sidesteps the self-rebuild problem entirely.** This container is never declared as a
  long-running compose service and is never itself "recreated" by `docker compose up -d` — it's a
  bare `docker run`, so there's no ordering puzzle about it rebuilding out from under itself.
- **Keeps elevated access transient.** "Can rewrite the source tree and rebuild everything" only
  exists for the few minutes an update is actually running, not permanently. This matches the
  least-persistent-privilege pattern already visible elsewhere in this codebase (read-only mounts,
  `SERVICE_NAME_RE` allowlisting).
- **The triggering HTTP request stays fast.** `POST /api/system/update/start` just fires
  `docker run -d ...` and returns immediately; it doesn't need to survive until the update
  finishes.
- Cost: one more small Dockerfile/image to build and keep in the compose file (as a
  never-`up`'d, `profiles: ["tools"]` entry, so it still gets rebuilt as part of the normal
  `docker compose build` pass and stays versioned with everything else).
- **Bootstrap gap:** the very first time, `alfr3d-service-updater:latest` has to exist on the host
  *before* the first automated update can run it — a one-time manual `docker compose build
  service-updater` when this ships. Every update after that rebuilds it as part of its own build
  step, so it stays current going forward.

### Option 2 — Persistent dedicated `service-updater` microservice, always running (fits the existing "one container per concern" pattern)

A small always-on FastAPI service, declared normally in `docker-compose.yml` like every other
`service-*`, with the repo mounted read-write and docker.sock mounted, exposing one internal-only
endpoint (no `ports:` — reachable only from other containers on the compose network).
`service-api` forwards `POST /api/system/update/start` to it internally instead of touching Docker
itself.

- Fits this repo's existing microservices convention better on paper, and shows up for free in
  the existing `/api/containers` health panel.
- **But reintroduces problem #3 in a worse form**: this service's own container *is* one of the
  things `docker compose up -d` recreates whenever its own image changes, including during the
  very update it's running. It has to update every other service first and do itself last as a
  deliberate "fire and forget, don't expect to survive to report completion" step, then have the
  *freshly recreated* instance read the shared status file on boot and re-publish "update
  completed" — a real ordering subtlety that Option 1 simply doesn't have.
- **Permanently increases attack surface** (rw repo + docker.sock, all the time) rather than only
  during an update, for a feature that fires maybe once every few days.

### Option 3 — Host-level script/systemd unit; `service-api` only signals it (trigger file or socket), never executes `git`/`docker compose` from inside any container

Keeps "can rewrite source + rebuild everything" off every container's surface entirely — the
strongest isolation of the three.

- Breaks the "everything is compose-declared, `git clone && docker compose up -d` is the whole
  deployment" model this repo has followed everywhere else. Needs a host-side systemd unit
  installed outside the compose stack — exactly the kind of manual host setup this feature exists
  to eliminate.
- Worse fit for the packaged "ALFR3D Kit" (`todo_alfr3d_kit_pi5_bom.md`) — a Pi 5 image would need
  this systemd unit baked into first-boot provisioning rather than just shipping inside the repo.
- Hardest of the three to develop/test locally (needs a real systemd environment, not just
  Docker).

### Recommendation: **Option 1.** Cleanest solve for the self-rebuild problem, keeps elevated access transient, and stays inside the "everything is in docker-compose.yml" model. Going with this unless next session's implementer finds a concrete blocker.

## Concrete design (Option 1), for next session to build against

### New files
- `services/service_updater/Dockerfile` — small image: `FROM docker:27-cli` (official Docker CLI
  image; ships `docker` **and** the `compose` v2 plugin out of the box, avoiding the exact
  v1/v2-mixing trap `todo_compose_container_name_collision.md` already got bitten by) +
  `apk add --no-cache git bash jq`. `COPY run_update.sh` in, `ENTRYPOINT ["/run_update.sh"]`.
- `services/service_updater/run_update.sh` — the sequence (below).
- `docker-compose.yml` addition:
  ```yaml
  service-updater:
    profiles: ["tools"]   # built, never started by `docker compose up -d`
    build:
      context: ./services/service_updater
  ```
- New named volume `update_status_data`, mounted read-write into the ephemeral updater run and
  read-only into `service-api` (api only ever reads it).

### The docker-from-docker path gotcha (write this down now, it will cost real time otherwise)
When `service-api` issues `docker run -v <src>:<dst> ...` against the host's docker.sock, `<src>`
is resolved by the **Docker daemon on the host**, not by paths inside `service-api`'s own
container. Passing `/project` (service-api's own mount point) will silently bind-mount a
directory that doesn't exist that way on the host. The host path (e.g.
`/home/athos/Projects/Alfr3d/alfr3d`) has to be known explicitly — add a `HOST_REPO_PATH` value to
`.env`, read it in `service-api`, and use it (not `/project`) when constructing the `docker run`
command.

### New/changed API surface (`service-api`)
- `GET /api/system/update-check` (Phase 1, no auth needed — same read-only tier as `/api/system/
  network`) → `{current_version, latest_tag, latest_title, release_notes_url, release_body,
  published_at, update_available}`. Backed by an in-memory cache refreshed on an interval (see
  below), so the endpoint itself never calls GitHub synchronously.
- `POST /api/system/update/start` (Phase 2, `Depends(require_permission("system", "update"))`) →
  checks the status file isn't already `"running"`, then:
  ```python
  subprocess.Popen([
      "docker", "run", "-d", "--rm",
      "--name", "alfr3d-updater-run",
      "-v", f"{HOST_REPO_PATH}:/repo",
      "-v", "/var/run/docker.sock:/var/run/docker.sock",
      "-v", "update_status_data:/status",
      "-e", f"TARGET_TAG={target_tag}",
      "alfr3d-service-updater:latest",
  ], env=env)
  ```
  returns `{"message": "Update started", "target_tag": target_tag}` immediately — no waiting on
  the subprocess.
- `GET /api/system/update/status` (Phase 2) → reads and returns `/status/update_status.json`
  (mounted read-only into service-api too).
- New WS channel `"update_status"`: **the ephemeral container has no FastAPI app and can't call
  `manager.broadcast` itself**, so `service-api` polls the status file every ~3s while it shows
  `"running"` and re-broadcasts what it reads — keeps the updater script's job to exactly "run
  the update, write a file," nothing network-facing.

### `run_update.sh` sequence
```
1. flock the lock file on /status — refuse a second concurrent run.
2. write_status(running, "fetch")
3. cd /repo; PREV_SHA=$(git rev-parse HEAD)
4. git fetch origin main --tags
5. git checkout "tags/${TARGET_TAG}"          # see detached-HEAD note below
6. write_status(running, "build")
7. docker compose build
   -> on failure: write_status(failed, "build", log_tail); git checkout "$PREV_SHA"; exit 1
      (running containers were never touched -- this is the safe, expected failure path)
8. write_status(running, "migrate")
9. docker compose --profile test run --rm migrate
   -> on failure: write_status(failed, "migrate", log_tail); exit 1
      (images were rebuilt but old containers are STILL RUNNING the old code against the
      old schema -- correct and safe, just needs a human to look; do not attempt `up -d`
      against a schema the running code doesn't expect)
10. write_status(running, "recreate")
11. docker compose up -d
12. write_status(running, "healthcheck")
13. poll `docker ps --filter name=alfr3d --format '{{.Names}}\t{{.Status}}'`
    for up to N minutes, watching for every alfr3d-* container to report "healthy"/"Up"
14. write_status(success or failed, "done", log_tail)
```

**Detached HEAD note:** step 5 leaves the repo on a detached HEAD at the release tag, on purpose
(we want the working tree to match exactly what the release notes described, not whatever `main`
has drifted to since). Document this in the repo somewhere a future human SSHing in would see it
— a bare `git pull` on a detached HEAD confusingly no-ops/errors, which will look like a bug the
first time someone hits it if it isn't written down.

### Rollback safety net (still not full auto-rollback — a non-goal — but cheap to add)
Right before step 7 (`docker compose build`), tag the current images:
`docker compose images -q <service>` → `docker tag <image> alfr3d-<service>:pre-update` for each
service. If a build *succeeds* and containers recreate, but the new version misbehaves in a way
healthchecks don't catch, a human can roll back fast — `git checkout $PREV_SHA` +
`docker tag alfr3d-<service>:pre-update alfr3d-<service>:latest` per service + `docker compose up
-d` — **without rebuilding from source again**. Worth the two extra lines even though scripting
the decision to roll back automatically stays out of scope.

### Frontend
- Phase 1: `UpdateBanner.jsx`, mounted at the top of the app layout (not nested in the collapsible
  System panel — a user may never open that). Polls `/api/system/update-check` (every few hours is
  plenty — releases don't ship more often than that). "Later" dismisses for the session only
  (`localStorage`, not permanent) so a dismissed banner doesn't silently suppress the *next*
  release too.
- System.jsx: add a "Version: 0.4.8 — up to date" / "0.4.8 → 0.4.9 available" row next to the
  existing services list, same `update-check` data.
- Phase 2/3: **Update Now** → confirm modal showing the release notes body (already returned by
  `update-check`) inline, so the "a human reads before triggering a rebuild" checkpoint lives
  here instead of disappearing → `POST /api/system/update/start` → banner switches to a progress
  view subscribed to the `"update_status"` WS channel (falling back to polling `GET /api/system/
  update/status` if the socket drops) → terminal state: success ("Updated to v0.4.9 ✅") or
  failure (show `log_tail`; the box is still running the previous version, which is the correct
  safe outcome for every failure path above).
- Gate the button the same way `System.jsx` already gates Restart (`isAuthenticated` +
  owner/technoking), backed for real by the `require_permission` check on the backend.

## Non-goals for v1
- **Automatic rollback.** Every failure path above leaves the previous state running/untouched
  and reports clearly — no unattended auto-revert. The pre-update image tags above make a manual
  rollback cheap; scripting the decision to do it is a future iteration.
- **Auto-apply without a click.** v1 is notify + manual confirm-with-release-notes, never silent
  auto-update.
- **`alfr3d_deck` (Android) self-update.** Goes through the Play Store already; out of scope here.
  Whether Deck should also surface this same banner (it talks to the same API) is a small
  follow-on, not part of this scope.
- **Staged/canary rollout, multi-NUC fleets.** Out of scope for a single-household box.
- **Fixing the `migrate` service's `"test"` profile name.** Documented above as a real oddity;
  not touching it in this todo.

## Testing plan before this ever touches the real NUC
This is production home-automation infrastructure — the container-restart/RBAC precedent this
plan leans on is well-tested, but *this* feature can rebuild every image and (per the new finding
above) run real migrations, so verify off-NUC first:
1. Unit-test the new routes with `docker`/`git`/subprocess calls mocked, same style as existing
   route tests.
2. **Local dry run in a scratch clone** (not the NUC): clone the repo into a throwaway directory,
   point a scratch `docker-compose.yml` copy's bind mount at it, cut a throwaway tag
   (`v0.0.0-test1`), and run `run_update.sh`'s full sequence there — including a deliberately
   broken build (bad Dockerfile edit on the test tag) to confirm the abort-and-restore path in
   step 7 genuinely leaves the previous containers alone, and a deliberately broken migration to
   confirm step 9's failure path does too.
3. Only after that passes clean, do one real run on the NUC — pick a **trivial, non-schema
   release** as the very first one pushed through this mechanism (a docs-only patch bump), not
   anything with a migration attached, mirroring how the zookeeper/kafka volume migration in
   `todo_compose_container_name_collision.md` was verified (byte-identical checks) before being
   trusted with real data.
4. Confirm `/api/containers` goes green for every service post-recreate before calling the feature
   done — step 12/13's healthcheck poll is exactly this, automated; the manual test is really
   "does it correctly catch it when something *doesn't* go green."

## Open questions for whoever implements this
1. Does the GitHub release-polling interval belong in `service-daemon` (already owns "background
   loop that runs periodically") or as a lightweight interval inside `service-api`? Independent of
   the Option 1 decision above — either can own the *check*; only the *execution* needed the
   architecture debate.
2. Should **Update Now** require re-entering a password (mirroring the existing admin
   password-reset confirm flow from `todo_household_admin_ui.md`), given the blast radius, or is
   session + confirm-dialog-with-release-notes enough? Leaning "no, the release-notes confirm is
   the checkpoint" but worth a second opinion before building.
3. Healthcheck-poll timeout in step 12/13 — how long is "too long" before reporting failure?
   Slowest existing healthcheck `start_period` in `docker-compose.yml` today is 120s
   (`service-daemon`); the update poll should be comfortably longer than the slowest single
   service's own boot healthcheck, not an arbitrary round number.

## Session checklist (start here next time)
1. Build `services/service_updater/` (Dockerfile + `run_update.sh`), add the `service-updater`
   entry to `docker-compose.yml`, add the `update_status_data` volume, one-time manual
   `docker compose build service-updater` to bootstrap the image.
2. Add `HOST_REPO_PATH` to `.env`/`.env.example`.
3. Phase 1: `GET /api/system/update-check` + `UpdateBanner.jsx` + System.jsx version row. Ship and
   verify this alone before touching Phase 2 — it's zero-execution-risk and immediately useful.
4. Phase 2: `POST /api/system/update/start`, `GET /api/system/update/status`, the `"update_status"`
   WS channel, `require_permission("system", "update")`. Run the full off-NUC dry run (Testing
   plan step 2) before wiring the frontend button to it.
5. Phase 3: confirm-modal + progress UI wired to Phase 2. Then, and only then, the real
   trivial-release NUC test (Testing plan step 3).
