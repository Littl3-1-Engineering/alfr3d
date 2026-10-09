# LF-1a: Lift the SA engine out of the daemon into `service_sa`

> **Layer:** awareness runtime · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-1a

## Status: 🔲 Not started (planned 2026-10-09)

## Why

`service_daemon` should be a fast loop engine. Today it also builds the context frame, runs ~25
SA rules, does card suppression, publishes SA cards and runs `compute_entity_baselines()` (~175 s
on the NUC, blocking the loop while it runs). SA moves to its own service so the daemon has no
long queries and SA can own its learning.

**No behaviour change in this phase.** The same cards must appear before and after.

## Scope

- [ ] New `services/service_sa/` mirroring the `service_daemon` layout, reusing `common/` DB,
      Kafka and timezone helpers. One image, two entrypoints:
  - `sa-awareness`: frame + rules + suppression + publish.
  - `sa-learner`: for now only the existing `compute_entity_baselines()` on its 6 h schedule.
- [ ] Move from `services/service_daemon/alfr3ddaemon.py`, as-is:
      `build_context_frame` (~782), `decide_displays` (~859), `DISPLAY_RULES` (~690),
      `_card_suppression_reason` (~918), every SA `check_*(frame)` rule (1036-2611),
      `publish_sa` (~2678), `compute_entity_baselines` and `_departure_hours_by_bucket`
      (~2788-3154), plus `utils/context_frame.py` and the helpers only they use.
- [ ] Remove those from the daemon, and the baseline job from its schedule (~3205-3212). The
      daemon keeps schedules, routines, arp scan, IoT/calendar/ESPHome sync and mute.
- [ ] In `sa-awareness`, subscribe to Kafka `event-stream` and keep household state in memory
      wherever an event already carries it (presence came/went and geofence, device turned_*,
      routine executed, track play_start/stop, calendar created/removed). Keep the existing small
      reads where no event exists yet; list those reads in this doc as follow-ups.
- [ ] `docker-compose.yml`: `sa-awareness` and `sa-learner` entries with healthchecks (pattern from
      `169de1bd`) and CPU limits for the 4-core NUC.
- [ ] Move the matching tests out of `tests/test_daemon_service.py` into a new
      `tests/test_sa_service.py`.

## Verify

- Full pytest suite and `lint.sh` green.
- Card parity: record the `situational-awareness` topic for a period before the switch and after;
  the same rule ids fire under the same conditions. `service_api` `consume_sa` is unchanged.
- Daemon cycle time drops, and no 6 h stall remains.
- Deploy to the NUC after a backup; watch both containers' health for a day.
