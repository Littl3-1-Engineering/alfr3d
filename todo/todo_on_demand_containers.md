# On-demand containers: stop running everything all the time

## Status: 🟡 service-tls one-shot + idle state written and verified off-NUC 2026-10-28 (unit tests + real Docker scratch project); **not yet deployed to the NUC**. sa-learner deferred; nginx-into-frontend and the updater fix are planned, not started.

## Measurements (NUC `Alfr3d-Gorsion`, 4 cores, 7.5 GiB RAM, taken 2026-10-28 08:34)

Host: 3.75 GiB used, 3.7 GiB available. Compose v5.5.1 (v2 lineage). All 16 services healthy.
CPU is ~0-3% everywhere, so **RAM is the only real cost**:

| Container | Mem | Notes |
|---|---|---|
| kafka | 1.09 GiB | left alone |
| mysql | 786 MiB | left alone |
| zookeeper | 231 MiB | KRaft note only |
| sa-learner | 168 MiB | candidate 2 |
| service-api | 147 MiB | left alone |
| service-daemon | 123 MiB | left alone |
| sa-awareness | 111 MiB | left alone |
| service-frontend | 40 MiB | candidate 3 |
| service-tls | 27 MiB | candidate 1 |

**Honest sizing:** all three candidates together are ~235 MiB (~3% of RAM) and ~0% CPU. This pass
is about shrinking the always-on privileged surface (service-tls holds `docker.sock` + host
network permanently) and process count, not about performance. The big RAM win is Kafka+ZK
(~1.3 GiB), which this pass does not touch.

## Candidates

### 1. service-tls  -> boot one-shot + host cron (implement first)

- **Current cost:** a Python 3.14 process looping every 60s (`TLS_CHECK_INTERVAL`), host network,
  `docker.sock` mounted permanently. The leaf is valid 365d, renewed <30d out, and only changes when
  host IPs/names change, so ~1439 of 1440 wakeups per day are no-ops.
- **Trigger:** `TLS_ONESHOT=1` run (reconcile once, exit 0), launched by `docker compose` at stack
  start (nginx `depends_on: service_completed_successfully`) and by a **host user-crontab** entry
  daily, matching `setup/db_backup_daily.sh` / `setup/host_usage.sh` (the NUC uses user cron, no sudo).
- **Behaviour change to decide:** today an IP change heals within 60s; with daily+boot it can take up
  to 24h, during which the Deck (pinning the CA, hostname check relaxed) still works but browsers
  would see a SAN mismatch. Recommended: the cron script is a cheap host-side check (`ip -o addr`
  hash vs a state file) run every 5 min that only launches the container when addresses changed,
  plus the daily run for expiry. That keeps near-60s healing at ~zero idle cost. **Your call:**
  strictly daily+boot as written, or the 5-min change check.
- **Failure modes:**
  - Container exits non-zero (CA volume unreadable, docker.sock unreachable): nginx never starts
    under `completed_successfully` on a cold boot. Mitigation: the one-shot exits 0 when an existing,
    valid leaf is already present and only reissue failed; non-zero only if there is no usable leaf.
  - `docker compose up -d nginx` alone re-runs the dependency (idempotent, fine).
  - An exited `service-tls` renders as DOWN on the dashboard (fixed in step 4).
  - nginx HUP skipped if `docker.sock` call fails: logged, leaf on disk is still correct, next run
    does not know to HUP again. Mitigation: cron wrapper also HUPs nginx whenever it re-issued.
  - Two overlapping runs (cron + boot): `flock` in the wrapper.
- **Rollback:** set `restart: unless-stopped` back, drop `TLS_ONESHOT`, restore nginx
  `condition: service_healthy`, remove the crontab line. `TLS_ONESHOT` unset keeps the old loop, so
  rollback is a compose edit + `docker compose up -d service-tls nginx`. **The `tls_ca` volume and
  CA key are never touched** (a regenerated CA forces every Deck to re-pair).

### 2. sa-learner  -> defer; measure first

- **Current cost:** Python + DuckDB + pyarrow process held resident (RSS unknown, see Measurements),
  `cpus: 1.0`. Real work is baselines every 6h (~175s), bronze export/silver/gold/learners nightly
  (minutes), disk sample every 4h; the rest is a 30s sleep loop.
- **Why not yet:** every job is `schedule`-driven and batch, so a timer-launched one-shot is feasible,
  but `todo/sa/SA_ROADMAP.md` still lists SA-12 transitions (re-check ~2026-11-01) and visitor-arrival
  learners, and the process owns a watchdog heartbeat the compose healthcheck depends on. Splitting
  it into three timers (`baselines`, `nightly`, `disk`) is a real refactor of `learner.py`, not a flag.
- **Trigger if we do it:** host cron running `docker compose run --rm sa-learner python learner.py --once <job>`.
- **Failure modes:** overlapping runs (a nightly run can outlast the 6h tick -> needs a lock); lost
  `first run 6h after start` semantics; cold-start import cost on each run; healthcheck/heartbeat
  and dashboard semantics change.
- **Rollback:** revert compose + remove cron entries; `learner.py` keeps the loop as the default.
- **Recommendation:** decide after the NUC `docker stats` numbers. If its idle RSS is small, skip it.

### 3. nginx -> merged into service-frontend (decided 2026-10-28; separate change, after service-tls)

Direction: **service-frontend stays, the `nginx` container goes.** The frontend image becomes the
edge: `nginx:alpine` + the built `dist/` + the reverse-proxy config. nginx is still the process
today, but the proxy is now a layer of the frontend image that can be swapped (Caddy, Traefik) without
touching the app or the compose topology.

- **Cost today:** two containers (node `serve` 40 MiB + nginx 4 MiB, 191 MB + 53 MB images) and a
  hop between them. `serve` and `npm install -g serve` leave the runtime image entirely.
- **Image:** `services/service_frontend/Dockerfile` final stage `FROM nginx:alpine`,
  `COPY --from=build /app/dist /usr/share/nginx/html/alfr3d`. Runs as root like the current nginx
  (binds 80/443; `certs/server.key` is `root:root 0600`). Unprivileged nginx is a later hardening.
- **Swap contract (document it in the Dockerfile header):** listens 80/443; reads certs from
  `/etc/nginx/certs`; static root for the SPA; proxies `/api/`, `/ws` to `service-api:5001` through
  Docker DNS at request time; is reloadable by HUP. Any replacement proxy must meet these.
- **Compose:** `service-frontend` gains `ports: 80:80, 443:443`, the three nginx bind mounts
  (`./nginx.conf`, `./certs:ro`, `./nginx-server-common.conf`), nginx's healthcheck
  (`wget http://127.0.0.1/health`) and `depends_on: service-tls: service_completed_successfully,
  service-api: service_started`. Removed: the `nginx` service, port 8000, `user: 1001`, and
  `env_file: .env` (a static server facing the LAN has no reason to hold every secret in `.env`).
- **Config:** `location /` becomes `root /usr/share/nginx/html/alfr3d; try_files $uri $uri/
  /index.html;` plus `expires 1y` on `/assets/` and `expires -1` on `/index.html`. Use `expires`, not
  `add_header`: an `add_header` in a nested location silently drops the inherited security headers/CSP.
  `/api/`, `/ws`, `/health` untouched.
- **service-tls coupling (silent failure):** `reload_nginx()` finds its target by the compose label
  `service=nginx`, and if nothing matches it only logs "nginx not running yet". After the merge it
  would never HUP anything and a re-issued leaf would not load. Change the default
  `TLS_NGINX_SERVICE` to `service-frontend`, set it explicitly in compose, and add a test.
- **NUC `nginx.conf`:** keep it as the bind-mounted file (gitignored, NUC-specific, includes the
  Tailscale `:443` block). Edit both `location /` blocks by hand; no other part changes. Back it up first.
- **Cutover hazard (updater):** `run_update.sh` runs `docker compose up -d` with no `--remove-orphans`.
  A release carrying this change would leave the old `nginx` container holding 80/443, the new
  `service-frontend` could not bind, and the updater would roll back. **Do this cutover by hand on the
  NUC first**, and put it in RELEASE_NOTES: `docker compose rm -sf nginx` before the first `up`.
- **Cutover sequence (expect ~10-30s web/Deck outage, ports flip):** build the new image
  (no port clash); edit `nginx.conf`; `nginx -t` via `docker compose run --rm --no-deps -T service-frontend
  nginx -t` with no port publish; `docker compose rm -sf nginx`; `docker compose up -d service-frontend`.
  Verify on LAN and Tailscale hostnames: `/`, a deep link + hard refresh, hashed asset headers (cache +
  CSP present), a missing asset, `/api/health`, `/ws`, the Deck still connects without re-pair, and
  force a leaf re-issue to confirm the HUP lands in `service-frontend`.
- **Failure modes:** `try_files` typo breaks deep links; the header-inheritance trap; port 80/443
  already bound (orphan nginx); `VITE_API_BASE_URL` is baked at build time (already unset on the NUC,
  confirm the bundle's API base is unchanged); anything still addressing `nginx` by name
  (grep found nothing in code, only `TLS_NGINX_SERVICE`); `k8s/` and `tests/docker-compose.yml` keep
  their own definitions (leave, note).
- **Rollback:** restore the `nginx.conf` backup and the previous compose/Dockerfile,
  `docker compose rm -sf service-frontend && docker compose up -d service-frontend nginx` on the old
  files. Do `docker compose rm` of the new container before the old nginx starts, so the ports are free.
- **Dashboard:** nothing on-demand here; the `nginx` row simply disappears from `/api/containers`.

## Self-service updater must keep working (todo/todo_selfservice_release_update.md)

Read `services/service_updater/run_update.sh` end to end 2026-10-28. Findings, in order of severity:

1. **The running updater is the OLD release's script.** The updater image is rebuilt during an update
   but only used by the *next* one, so the first update that crosses a topology change is driven by
   the previous version's logic. Any fix that lives only in `run_update.sh` is too late for the
   crossing release.
2. **Orphan `nginx` blocks the merge.** `docker compose up -d` has no `--remove-orphans`; the old
   `nginx` keeps 80/443, `service-frontend` can't bind, healthcheck times out, rollback. Fix lives in
   compose, not the script (so it works under any updater version, and for a hand-run `up`):
   a `legacy-cleanup` one-shot (`docker:27-cli`, docker.sock, `restart: "no"`) that finds its own
   project label via `docker inspect $HOSTNAME` and `docker rm -f`s any container with that project
   and `service=nginx`, idempotent when none exists. `service-frontend` gets
   `depends_on: legacy-cleanup: service_completed_successfully`. Delete the service two releases later.
3. **Rollback restores old images under the NEW compose file.** The failure paths after `migrate`
   call `rollback_images` then `docker compose up -d` without `git checkout "$PREV_SHA"` (only the
   build/migrate failures check it out). Across this change that yields an old node `serve` image
   with new 80/443 ports and a `/health` healthcheck on :80 -> never healthy -> "manual intervention
   needed". Same flaw for the service-tls one-shot (old looping image never completes, so nginx
   would wait forever). Fix: checkout `$PREV_SHA` before `rollback_images` in both rollback paths so
   the compose file matches the images. With the old compose, compose recreates `service-frontend`
   first (frees 80/443) and then starts `nginx`, because nginx depends on it.
4. **Health gate is fine for one-shots.** `wait_for_healthy` uses `docker ps` without `-a`, so exited
   one-shots (`service-tls`, `legacy-cleanup`) are not counted as unhealthy. Keep it that way;
   add a test/comment so nobody "fixes" it with `-a`.
5. **Dirty NUC checkout will abort the first real update.** `git checkout tags/X` fails when tracked
   files the tag changes (e.g. `docker-compose.yml`) are locally modified, and the NUC currently has
   such changes (HEAD `cbc73c72`, 10+ modified files). It fails safely ("tag not found"), but the
   first Update Now cannot succeed until that tree is clean. Precondition, not a code change.
6. **Web UI blips during every update.** The frontend is now the edge and a build-based service, so it
   is recreated on any frontend image change (stock-image nginx was not). service-api restarts
   anyway, so the update-status poll already tolerates it; verify in the dry run.

**Release sequencing:** N = updater rollback fix only (item 3). N+1 = service-tls one-shot + idle state +
nginx-into-frontend + `legacy-cleanup`. N+2 or later = remove `legacy-cleanup`. A household that skips
N runs an older script for N+1: the forward path still works (item 2 is in compose), only automatic
rollback is weaker; say so in RELEASE_NOTES. The NUC itself does the cutover by hand first.

**Proof before release:** off-NUC dry run like the original (scratch compose project name, remapped
ports): (a) update from tag N to N+1 driven by N's script, success path; (b) same with a forced
unhealthy new frontend to exercise rollback across the boundary and confirm the old stack returns;
(c) update with a pre-existing `nginx` container to prove `legacy-cleanup`; (d) re-run with no
`nginx` to prove idempotence.

## Left alone (agreed)

kafka, zookeeper, mysql, redis, service-api, service-daemon, service-device, service-user,
service-environment, service-speak, sa-awareness: always-listening consumers, timers, or shared
dependencies. Kafka KRaft (drops zookeeper) is noted only; not touched in this pass.

## Dashboard / API: "idle" state

`GET /api/containers` and the Core/ContainerHealth UI currently map `exited` -> DOWN. Plan: a compose
label `alfr3d.ondemand=true` on intentionally on-demand services. `fetch_container_metrics()` reports
`"ondemand": true` per container (label read from the same `docker inspect` call), and
`containerStatus()` returns a new `IDLE` status (tier `ok`) for an `exited` container with
`ondemand` set and exit code 0. A non-zero exit on an on-demand container is still DOWN.

## nginx.conf: what to merge by hand on the NUC (verified over ssh 2026-10-28)

The NUC's `nginx.conf` has **diverged heavily** from `nginx.conf.example` and does **not** use
`nginx-server-common.conf` at all: it has its own `:80` (301 to https), `:443` for
`localhost alfr3d.local _` using `server.crt`, and a separate `:443` block for the Tailscale host
using `ts.crt`/`ts.key` (managed outside service-tls). It already serves the leaf from
`/etc/nginx/certs/server.crt`, so **the service-tls one-shot needs no nginx.conf merge.** Do not
copy the example over it. Any later frontend-into-nginx change must be applied to both of the
NUC's `location /` blocks by hand.

Other NUC facts that constrain the implementation:
- `certs/server.key` and `server.crt` are `root:root`; the container (root) writes them, so the host
  trigger must go through `docker compose run`, never write them directly as `alfr3d`.
- The NUC working tree is **dirty** (`docker-compose.yml`, `learner.py`, etc. modified, HEAD
  `cbc73c72`), so deploy by patch/targeted file copy, never `git checkout`/`pull` over it.
- Leaf SANs include the Tailscale IP (`100.77.158.32`), so an address-change check must hash all
  interfaces, not just the LAN one. `flock` and `ip` exist on the host.
- User crontab already has `db_backup_daily.sh` (04:00) and `host_usage.sh` (every 4h).

## Work items

- [x] NUC `docker stats` / `docker compose ps` measured 2026-10-28.
- [x] Decided 2026-10-28: strictly daily + boot (no 5-min check), plus a manual `setup/tls_reissue.sh`. Boot is covered by `alfr3d.service` (`docker compose up -d` runs the one-shot as nginx's dependency); only the daily run needs a crontab line.
- [x] service-tls one-shot (`TLS_ONESHOT`), compose `restart: "no"` + `service_completed_successfully`, healthcheck dropped (an exited container can't be healthy).
- [x] `setup/tls_reissue.sh` + README maintenance section. [ ] crontab line on the NUC (`30 4 * * * /home/alfr3d/alfr3d/setup/tls_reissue.sh >> /home/alfr3d/db_backups/tls.log 2>&1`) once deployed.
- [x] `tests/test_tls_oneshot.py` (7) + 2 in `tests/test_local_tls.py`.
- [x] `alfr3d.ondemand` label, `ondemand`/`idle` on `/api/containers`, `idle` on `/api/system/services` (Service Control dot), `IDLE` in `containerStatus.js`; `tests/test_containers_route.py`, `containerStatus.test.js`.
- [x] Update `todo/todo_local_ca_cert_rotation.md`; README mention of `service_tls` + `/api/tls/*`
      (AGENTS.md already has it, README does not).
- [ ] Updater: rollback checks out `$PREV_SHA` (release N), `legacy-cleanup` one-shot, dry runs a-d above, clean NUC tree before first Update Now.
- [ ] Follow-up: sa-learner decision after measurements; nginx-into-service-frontend change (candidate 3).
