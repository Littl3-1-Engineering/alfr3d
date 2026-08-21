# Todo: Init Scripts for Container Autostart on Device Boot

## Status: 🔲 Not started

## Goal
Add init scripts so all ALFR3D containers (Kafka, MySQL, Redis, service_api, service_daemon, service_speak, service_frontend, etc.) start automatically when the host device boots, without a manual `docker compose up`.

## Notes / Approach
- [ ] Decide mechanism: systemd unit calling `docker compose up -d` in the project directory vs. Docker's own `restart: unless-stopped`/`restart: always` policies in `docker-compose.yml` vs. `docker compose` as a systemd-managed service.
- [ ] Confirm current `docker-compose.yml` restart policies (if any) — likely need `restart: unless-stopped` added per service as a baseline regardless of the boot mechanism chosen.
- [ ] If systemd: write a `.service` unit (e.g. `alfr3d.service`) that runs `docker compose -f <path>/docker-compose.yml up -d`, enable it, and document install steps in the README.
- [ ] Handle startup ordering/dependencies (DB/Kafka ready before dependent services) — check whether `depends_on` + healthchecks in `docker-compose.yml` are sufficient or whether a wait-for script is needed.
- [ ] Test on the actual target device (reboot and confirm all containers come up healthy with no manual intervention).
- [ ] Document the autostart setup in the README's Deployment section.
