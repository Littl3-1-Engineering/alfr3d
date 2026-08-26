# Todo: Init Scripts for Container Autostart on Device Boot

## Status: ✅ Shipped and reboot-tested 2026-08-25 — full stack confirmed autostarting unattended

## Goal
Add init scripts so all ALFR3D containers (Kafka, MySQL, Redis, service_api, service_daemon, service_speak, service_frontend, etc.) start automatically when the host device boots, without a manual `docker compose up`.

## Notes / Approach
- [x] Decide mechanism: systemd unit (`alfr3d.service`, see `setup/alfr3d.service`) calling `docker compose up -d` on top of Docker's own `restart: unless-stopped` policies as the baseline — explicit and works even on a fresh device where containers don't exist yet.
- [x] Confirm current `docker-compose.yml` restart policies — `zookeeper`, `kafka`, `redis`, and `mysql` were all missing `restart: unless-stopped` (every app-level service already had it); added 2026-08-22.
- [x] Systemd unit written: `setup/alfr3d.service`, template `WorkingDirectory=/opt/alfr3d` — edit to the actual repo path before installing (see README's new "Autostart on Boot" section for install steps).
- [x] Startup ordering: existing `depends_on` + `healthcheck` in `docker-compose.yml` already sequences DB/Kafka readiness before dependents — no separate wait-for script needed.
- [x] Installed and enabled on the NUC (`alfr3d@192.168.2.200`, repo at `/home/alfr3d/alfr3d`) 2026-08-22: `/etc/systemd/system/alfr3d.service` with `WorkingDirectory=/home/alfr3d/alfr3d`, `systemctl enable --now`'d. `docker.service` was already enabled at boot there.
- [x] Test with an actual reboot of the NUC to confirm the full stack comes up unattended — done 2026-08-25 with explicit user go-ahead (`sudo systemctl reboot`). All 12 containers back up within 30s (mysql/kafka/redis/nginx healthy), `/api/iot/status` and the frontend (port 8000) both confirmed responding post-reboot.
- [x] Document the autostart setup in the README (`### Autostart on Boot` under Setup and Maintenance).

## Side finding while applying this on the NUC (2026-08-22)
Applying the restart-policy fix surfaced pre-existing container/volume drift on the NUC, unrelated to this todo but now cleaned up:
- `zookeeper` and `redis` containers had anomalous raw-container-ID-prefixed names (e.g. `8f46eadb3934_alfr3d-zookeeper-1`) instead of the normal Compose naming — leftover from some earlier interrupted `docker compose up`. This blocked Compose from recreating them. Fixed by removing and letting Compose recreate cleanly under standard names.
- Kafka's `/var/lib/kafka/data` has no named volume (by design — topics are ephemeral, recreated via `KAFKA_CREATE_TOPICS` on boot) but was sitting on an orphaned *anonymous* volume that Compose kept reusing across recreates, carrying a stale internal cluster ID. After zookeeper got a fresh cluster ID, Kafka refused to start (`InconsistentClusterIdException`) until that anonymous volume was removed (`docker rm -v`) and Kafka got a truly fresh one.
- `docker volume ls` on the NUC shows several other unlabeled hash-named volumes (plus `pgdata`/`pgodindata`, which look unrelated to alfr3d — likely a different project on the same host). Didn't touch these; worth a separate look sometime with `docker system df`/`docker volume ls` to see what's actually orphaned vs. in use, but out of scope here.
