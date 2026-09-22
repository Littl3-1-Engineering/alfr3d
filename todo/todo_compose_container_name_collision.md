# Compose recreate trap: containers stuck under their own backup name

## Status: 🟢 Fixed on the production NUC 2026-09-22; prevention + the zookeeper volume follow-up still open

Found while adding container healthchecks (`docker compose up -d --no-deps zookeeper` failed
outright). Not caused by that work — the containers had been in this state since 2026-09-12.

## What happened

`mysql`, `redis` and `zookeeper` were running under hash-prefixed names:

```
2a2c09387c6c_alfr3d-mysql-1
f71909159f7d_alfr3d-redis-1
0172ec41c310_alfr3d-zookeeper-1
```

All three reported `StartedAt = 2026-09-12T16:00:43`, i.e. one event, not three — consistent
with the docker-compose v1/v2 mix-up recorded for that date.

**This was not cosmetic. All three were un-recreatable by compose.**

## Mechanism

To recreate a container, compose renames the existing one to `<container-id-prefix>_<name>`
as a backup, creates the replacement, then deletes the backup. If that sequence is
interrupted, the container keeps the backup name permanently.

From then on the rename is self-referential: compose tries to rename
`0172ec41c310_alfr3d-zookeeper-1` to its backup name — which, since the id prefix is
unchanged, is `0172ec41c310_alfr3d-zookeeper-1` — and Docker refuses:

```
Error response from daemon: Conflict. The container name "/0172ec41c310_alfr3d-zookeeper-1"
is already in use by container "0172ec41c31093dca..."
```

The failure is safe (the running container is never stopped) but total: **any** future
`docker compose up -d` touching those services fails the same way, so they silently stop
receiving config changes while everything looks fine in `docker ps`.

### Second-order effect

`/api/containers` filtered with `container_name.startswith("alfr3d")`, so all three were
missing from the Nexus container-health panel entirely — 10 containers shown instead of 13.
Fixed the same day by matching `"alfr3d" in name`; the filter should stay substring-based
precisely because this state can recur.

## Fix applied (2026-09-22)

`docker rename` back to the canonical name. This is metadata-only — it does not stop,
restart or otherwise disturb the container (verified: identical container id and `StartedAt`
before and after, volumes still attached, `Up 10 days` preserved).

```
docker rename 0172ec41c310_alfr3d-zookeeper-1 alfr3d-zookeeper-1
docker rename 2a2c09387c6c_alfr3d-mysql-1     alfr3d-mysql-1
docker rename f71909159f7d_alfr3d-redis-1     alfr3d-redis-1
```

Confirmed resolved with a non-destructive
`docker compose up -d --no-deps --dry-run --force-recreate mysql redis zookeeper`, which now
plans a clean recreate for all three instead of erroring.

Zookeeper was then actually recreated (to pick up its new healthcheck) and verified: same
data volume reattached, all 9 Kafka topics intact, ZK node count unchanged at 171.

## Open follow-ups

### 1. Zookeeper's data is on an anonymous volume — the real remaining risk

`mysql` and `redis` use named volumes (`alfr3d_mysql_data`, `alfr3d_redis_data`). Zookeeper
does not: `/var/lib/zookeeper/data` and `/var/lib/zookeeper/log` are **anonymous** volumes
created by the image's own `VOLUME` directive, with random hash names.

Compose v2 preserves anonymous volumes across an ordinary recreate, so this is survivable
today — but a single `docker compose down -v`, or `up -V` / `--renew-anon-volumes`, silently
starts ZK with an empty data dir. Kafka's topic metadata, consumer group offsets and broker
registration all live in ZK, so that is a full event-bus loss with no obvious warning.

Add named volumes to the `zookeeper` service in `docker-compose.yml`, matching the pattern
the other stateful services already follow. Migrating means copying the current anonymous
volume's contents into the new named one during a recreate, not just editing the file — the
old data does not follow a mount-point change on its own. A backup taken 2026-09-22 is at
`~/zk_backup/zk_data_20260922_123733.tgz` on the NUC.

### 2. Detection

Nothing surfaced this for ten days. A check worth having:

```
docker ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]{12}_'
```

Non-empty output means at least one container is stranded under a backup name. Worth folding
into whatever health/ops sweep runs against the NUC, since the symptom is invisible in
`docker ps` and in the dashboard.

### 3. Root cause prevention

The originating incident is already recorded: never mix `docker-compose` (v1) and
`docker compose` (v2) against the same project — use v2 for build and recreate together.
This todo is the downstream damage from that, found ten days later.
