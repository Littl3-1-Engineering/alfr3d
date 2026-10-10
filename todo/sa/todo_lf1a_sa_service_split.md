# LF-1a: Lift the SA engine out of the daemon into `service_sa`

> **Layer:** awareness runtime · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-1a

## Status: 🟢 Deployed to the production NUC 2026-10-09 (commit on `feat/sa-learning-foundation`)

`service-daemon` no longer runs any SA. `sa-awareness` (60 s card loop) and `sa-learner`
(`compute_entity_baselines` every 6 h) run from the new `service_sa` image and have been healthy
since deploy.

## Why

`service_daemon` should be a fast loop engine. Today it also builds the context frame, runs ~25
SA rules, does card suppression, publishes SA cards and runs `compute_entity_baselines()` (~175 s
on the NUC, blocking the loop while it runs). SA moves to its own service so the daemon has no
long queries and SA can own its learning.

**No behaviour change in this phase.** The same cards must appear before and after.

## Scope

- [x] New `services/service_sa/` mirroring the `service_daemon` layout, reusing `common/` DB,
      Kafka and timezone helpers. One image, two entrypoints:
  - `sa-awareness`: frame + rules + suppression + publish.
  - `sa-learner`: for now only the existing `compute_entity_baselines()` on its 6 h schedule.
- [x] Move from `services/service_daemon/alfr3ddaemon.py`, as-is:
      `build_context_frame` (~782), `decide_displays` (~859), `DISPLAY_RULES` (~690),
      `_card_suppression_reason` (~918), every SA `check_*(frame)` rule (1036-2611),
      `publish_sa` (~2678), `compute_entity_baselines` and `_departure_hours_by_bucket`
      (~2788-3154), plus `utils/context_frame.py` and the helpers only they use.
- [x] Remove those from the daemon, and the baseline job from its schedule (~3205-3212). The
      daemon keeps schedules, routines, arp scan, IoT/calendar/ESPHome sync and mute.
- [ ] **Deferred to LF-1c:** In `sa-awareness`, subscribe to Kafka `event-stream` and keep household state in memory
      wherever an event already carries it (presence came/went and geofence, device turned_*,
      routine executed, track play_start/stop, calendar created/removed). Keep the existing small
      reads where no event exists yet; list those reads in this doc as follow-ups.
- [x] `docker-compose.yml`: `sa-awareness` and `sa-learner` entries with healthchecks (pattern from
      `169de1bd`) and CPU limits for the 4-core NUC.
- [x] Move the matching tests out of `tests/test_daemon_service.py` into a new
      `tests/test_sa_service.py`.

## Verify

- Full pytest suite and `lint.sh` green.
- Card parity: record the `situational-awareness` topic for a period before the switch and after;
  the same rule ids fire under the same conditions. `service_api` `consume_sa` is unchanged.
- Daemon cycle time drops, and no 6 h stall remains.
- Deploy to the NUC after a backup; watch both containers' health for a day.

## What actually happened (2026-10-09)

- **A pure move, verified as one.** `alfr3ddaemon.py` went 3278 → 565 lines. The SA constants,
  the 30-odd SA methods of `MyDaemon` (now `SAEngine`), `publish_sa` and
  `compute_entity_baselines` / `_departure_hours_by_bucket` moved verbatim into
  `service_sa/sa/engine.py` (cut by content anchors, not line numbers, after two off-by-one misses
  against the checks). `context_frame`, `mood_utils`, `focus_utils`, `routing_utils` moved to
  `service_sa/sa/`. 237 of the 297 daemon tests moved to `tests/test_sa_service.py` with only
  import/patch paths retargeted; total 690 passing (687 before + 3 new entrypoint tests).
- **Shared modules went to `common/`, not `service_sa`.** `calendar_utils` and `gmail_utils`
  are still needed by the daemon (`sync_calendar`, `sync_gmail`, startup) *and* by SA
  (`get_upcoming_events`, `check_unread_emails`), so they now live in `common/`.
  `service_daemon/utils/spotify_utils.py` was a thin facade over `common.spotify_utils`; its one
  unique function, `resolve_playlist`, moved into the common module and the facade was deleted.
- **Daemon edits**: removed the SA call from `run()`, the 6 h baselines schedule, the SA `test`
  CLI mode, and replaced the waking-hours `self.check_emails()` (an SA rule used for a side
  effect) with a direct `gmail_utils.check_unread_emails()` — same call, same effect.
- **A latent test bug fell out.** `TestSyncCalendarRoutine` passed only if an earlier test had
  already imported `alfr3ddaemon` with `KAFKA_BOOTSTRAP_SERVERS` set; run alone it failed on
  `main` too. It now sets its own environment.
- **Compose**: `sa-awareness` and `sa-learner` share one image (`service_sa/Dockerfile`), same
  host network / env / `secrets_data` mount as the daemon (SA reads Gmail and HA/ST credentials
  from `/secrets`). Each gets 1 CPU; the learner also gets half the CPU shares so a long fit can't
  starve card publishing on the 4-core NUC. Separate heartbeat files and healthchecks (learner
  window 900 s, because one baseline run measured ~175 s). `lint.sh` and `setup/build_images.sh`
  list the new service.
- **Parity check**: recorded the `situational-awareness` topic before the move and after.
  Same rules fire (`time`, `household_composition`, `rhythm_break_anomaly`, `music`,
  `guest_overstay_advisory`, `email`, `weather`, `mood`) with identical card shapes, and the topic
  contents match the new service's own publish log. The only rule absent after was `now_playing`,
  which is state, not a regression: Spotify reported nothing playing at the time, and
  `check_now_playing` returns nothing in that case (run directly against a live frame to confirm).
  **Unexplained**: the first "after" capture was missing `guest_overstay_advisory` as well, even
  though the service's log shows it published every cycle (it is also returned by a direct call,
  and not suppressed). A second capture matched the log exactly, so the likeliest cause is that
  first capture's timing, but that is a guess, not something I traced.
  `card_interactions` kept receiving `shown` events from the clients throughout (845 in the day).
- **Not verified**: `consume_sa` / the Nexus and Deck rendering were not looked at directly, only
  that the topic payload is unchanged and clients keep reporting against it. Daemon cycle time
  was not measured before/after; the 175 s baseline run now happens in the other container, so
  the loop can no longer be held up by it by construction.

## Deferred: LF-1c, event-driven state

The plan also asked `sa-awareness` to keep household state in memory from Kafka `event-stream`
and to read `sa_profiles` from memory. That is a behaviour change, not a move, and there is
nothing to hold in memory until LF-3 produces profiles. It is split out so this phase could stay
a verifiable no-behaviour-change move. Remaining small DB reads per cycle (context-frame
fetchers, `card_interactions` suppression lookup, config keys) are all indexed single-row or
short queries; list any that grow long here.
