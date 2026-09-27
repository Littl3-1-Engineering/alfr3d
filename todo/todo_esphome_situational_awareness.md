# SA-9: ESPHome sensors as a situational-awareness signal

## Status: 🟢 Phase 2's `climate_deviation` bug (found 2026-09-26) fixed and deployed the same
day; `climate_advisory` live and working; `ambient_occupancy` still blocked on hardware

**Update 2026-09-26 (fix deployed)**: fixed the gap below -- `compute_entity_baselines()` now
computes `typical_daily_min`/`typical_daily_max` for climate baselines as
`median +/- CLIMATE_BASELINE_STDEV_MULTIPLIER` (2.0) standard deviations instead of raw
min/max, and `CLIMATE_DEVIATION_MARGIN_C`/`_HUMIDITY_PCT` shrunk from 2.0/10 to 0.5/3 to match
(the margin only needs hysteresis now, not to compensate for an overly wide band). Commit
`4f024d90`, 2 tests updated/added, full daemon suite green (290 passed; the 2
`TestSyncCalendarRoutine` failures are pre-existing/unrelated). Built and pushed, then rebuilt
+ redeployed `service-daemon` on the real NUC the same session, and manually re-ran
`compute_entity_baselines()` against real production data to verify immediately rather than
waiting for the 6-hourly schedule. Real before/after for smarthome_device_id 37885
(temperature): night bucket went from a 21.37-29.75°C band (effectively ~19-32°C once margined
-- wider than the sensor's entire recorded range) to 21.64-30.91°C median +/- 2sd (effectively
~21.1-31.4°C margined). Confirmed the fix actually does something, not just in theory: the
household's real recorded 19.27°C morning low and 63.57% humidity peak both now fall *outside*
their bucket's learned band, so a repeat of either would fire `climate_deviation`; the current
live reading at deploy time (23.78°C / 49.65% humidity, both unremarkable) correctly falls
*inside* its band and does not fire. Not yet observed firing live on a genuine future deviation
-- same "built and verified, waiting on a real occurrence" category as SA-3 before its
2026-09-12 firing was found.

**Update 2026-09-26 (bug found)**: with 10 days of real `smarthome_sensor_history` accumulated (314k+ rows,
well past `CLIMATE_BASELINE_MIN_SAMPLES`), checked whether Phase 2's `climate_deviation` had
started firing. It hasn't — zero rows in `card_interactions` for that `rule_id`, ever. Root
cause is a design gap, not a data-volume one: `compute_entity_baselines()` sets
`typical_daily_min`/`typical_daily_max` to the raw observed min/max of the lookback window, and
`check_climate_deviation()` compares the live reading against that range ± a fixed margin
(`CLIMATE_DEVIATION_MARGIN_C = 2.0`). A min/max-based "typical" band self-widens to cover
whatever noise already happened to occur in the window, so it structurally converges toward
never firing rather than converging toward a tight, meaningful "typical" range. Confirmed
against real numbers: the night-bucket temperature baseline is already 21.37-29.75°C (close to
the sensor's entire 10-day observed range of 19.27-29.94°C), so with the margin the effective
trigger band is roughly 19-32°C — wider than anything the sensor has ever recorded. Same
mechanism applied to the humidity leg (baseline min/max ± 10 pts) -- fixed in the same pass, see
the "fix deployed" entry above. `climate_advisory` (Phase 1, fixed
thresholds) is unaffected and has been firing correctly on its own absolute thresholds
(120 rows 09-16→09-17, then correctly silent since as real indoor temp dropped below 27°C from
09-20 on — not a bug).

**Update 2026-09-16 (Phase 2, same day as Phase 1)**: `climate_advisory` (Phase 1) fired on fixed
absolute thresholds because there was no history to learn "typical" from. This phase builds that:
- New `smarthome_sensor_history` table (migration 040/0043) -- durable numeric-reading history,
  populated from `esphome_utils._upsert_node_entities()`/`_handle_state_push()` via the new
  `_record_sensor_history()` helper (best-effort, never breaks the state upsert it rides along
  with). Nothing existed before this; both the poll and push paths only ever overwrote
  `smarthome_devices.last_state` in place.
- `entity_baselines` gains `time_of_day_bucket` (`'all'/'morning'/'day'/'evening'/'night'`, reusing
  `common/timeofday.py`'s existing vocabulary) and `typical_median_value` (migration 041/0044).
  Room baselines (`entity_type='room'`, reserved since migration 033) key on the sensor entity's
  own `smarthome_devices.id`, documented as a deviation from a literal "room" since that column is
  never populated for any source (HA/ST/ESPHome).
- `compute_entity_baselines()` gains a fourth block computing per-sensor-entity,
  per-time-of-day-bucket baselines from the new history table (30-day lookback, 10-sample floor
  per bucket).
- New `context_frame.fetch_esphome_climate_baselines(bucket)` + `frame.esphome_climate_baselines`.
- New sibling rule `MyDaemon.check_climate_deviation()` (`DISPLAY_RULES` priority 5.4, right after
  `climate_advisory`) -- fires only when the current reading is outside the learned
  [min,max]±margin range for the current time-of-day bucket, and only once that bucket's baseline
  clears its own sample-count floor. Deliberately a new `rule_id`/mode, not a rewrite of
  `climate_advisory` -- same split as `weather`/`weather_advisory`, so dismissing one doesn't
  suppress the other and nothing about the already-shipped rule changed.

607 tests pass (24 new), `black --line-length=100`/`flake8 --max-line-length=100` clean. No
live-hardware verification this pass -- the baseline needs real accumulated history before it can
fire meaningfully; expected to stay silent on the real household for a while after deploy, not a
bug. No migration has been run against a real/disposable DB this pass either (no MySQL available
in this environment) -- run `alembic upgrade head` against a real or disposable DB before deploying
to confirm 0043/0044 apply cleanly, same verification gap flagged for the original ESPHome
migration until a prior session closed it.

## Status (previous): 🟢 Phase 1 shipped 2026-09-16 — `climate_advisory` rule live; `ambient_occupancy` still blocked on hardware

**Update 2026-09-16 (later same day)**: Phase 1 built and unit-tested. New
`context_frame.fetch_esphome_climate_snapshot()` reads the accepted node's temperature/humidity
entities out of `smarthome_devices.last_state` each cycle into `frame.esphome_climate`; new
`MyDaemon.check_climate_advisory()` (`alfr3ddaemon.py`, registered in `DISPLAY_RULES` at priority
5.3, between `weather` and `cross_surface_continuity`) fires a fixed-threshold comfort advisory
when temperature/humidity cross a hardcoded comfort band, gated on that reading's `online` flag
(the only freshness signal available -- `smarthome_devices` has no `updated_at` column) so a stale
reading from the sensor's flaky Wi-Fi link can't fire a card. Not baseline-learned -- no
`entity_baselines` support exists yet for smarthome/ESPHome entities. No frontend/Deck changes
needed -- both render it automatically through the existing generic card path. Full detail in the
session's implementation; see `services/service_daemon/utils/context_frame.py` and
`alfr3ddaemon.py`'s `check_climate_advisory`/`CLIMATE_ADVISORY_*` constants.

`ambient_occupancy` remains explicitly out of scope -- the only accepted ESPHome node has no
presence/motion-capable entity (temperature, humidity, wifi signal, status, light, power button
only). Stays blocked until a occupancy-capable sensor exists, unchanged from the original call
below.

## Status (previous, 2026-09-16 morning): 🟡 Phase 0's blocker resolved — real hardware now exists, Phase 1 not yet started

**Update 2026-09-16**: a real ESPHome node (Athom ESP32-C3 temp/humidity sensor) joined the
household LAN. `todo/todo_esphome.md`'s "Live-verified 2026-09-16" section confirms the base
integration (discovery, accept, poll sync) against this real device — the hard prerequisite this
doc's Phase 0 was blocked on. This doc's own Phase 1 (using it as an SA signal:
`climate_advisory`/`ambient_occupancy` rules, context-frame sensor fields) has **not** been
started — that's separate scope from validating the base integration, not done as a side effect of
this session's onboarding/bug-fix work. Revisit deliberately when picking this back up, and note
the device is a single sensor with an intermittent Wi-Fi presence (dropped offline mid-session) —
worth factoring into how much confidence any resulting SA rule should carry.

## Status (original): 🔴 Stopped at Phase 0 — no real ESPHome node available to validate against

Second item of Wave 3, following SA-6 (self-hosted routing, in progress). Builds on
`todo/todo_esphome.md` (Phases 0-4 shipped 2026-08-21) — the integration itself (discovery,
`services/common/esphome_utils.py`, sync, API routes) exists, but the task doc is explicit and
unusually emphatic that Phase 1 (live-hardware validation) is a hard prerequisite, not a nice-to-
have: *"Ship nothing downstream until this passes — building SA rules on an untested integration
repeats exactly the mistake the removed travel code made, where a feature existed in the codebase
and could never fire."*

## Phase 0 — investigate

- **Confirmed, on the real production LAN, not assumed**: SSH'd into the household's actual
  production box (`alfr3d@192.168.2.200`) and ran a real mDNS scan —
  `avahi-browse -rt _esphomelib._tcp` — the exact service type
  `services/common/esphome_utils.py`'s `discover_esphome_nodes()` listens for. **Zero devices
  found.** This household does not currently have a live ESPHome node on its network, so there is
  nothing real to validate the shipped integration against today.
- **Attempted a virtual substitute, genuinely, not skipped outright.** ESPHome supports a `host`
  compile target that runs entirely in software and still speaks the real native API/mDNS
  discovery protocol `esphome_utils.py` implements — a legitimate way to exercise this integration
  without physical hardware, the same spirit as SA-6's real-but-cleaned-up test on the NUC. Tried
  to set this up in this session's own environment: both `pip install esphome` and
  `docker pull esphome/esphome` stalled at a small fraction of normal transfer speed (a handful of
  MB over several minutes) — this environment's network path to those specific endpoints is
  unusually slow today, the same symptom SA-6 hit with `download.bbbike.org` (unrelated services,
  same environment — likely a local network/egress condition, not a coincidence about ESPHome
  specifically). Not pursued further within this pass's time budget once it became clear this
  wasn't a quick setup.
- **Checked one related fact while on the real box anyway**: the NUC has a real, working
  Bluetooth adapter (`hci0`, USB, `UP RUNNING`, confirmed via `hciconfig -a`/`rfkill list`) — not
  needed for this item, but directly relevant to SA-8 (BLE presence sensing), next on the list.

**Verdict: stop here, per the task doc's own explicit rule.** No real (or virtually substituted)
ESPHome node was reachable this pass to validate the shipped integration against. Building
Phase 2's context-frame sensor fields or Phase 3's `climate_advisory`/`ambient_occupancy` rules
on top of an integration that has *never* talked to a real device would be exactly the
speculative-feature mistake both this task doc and the removed travel code (SA-6's own
motivating history) warn against repeating.

## Not yet done

- **Live-hardware validation itself** — needs either a real ESPHome node on the household's LAN
  (none exists today) or a working `esphome` host-mode virtual device (blocked this pass by slow
  package/image downloads in this environment, not a fundamental blocker — worth retrying when
  network conditions differ, or when a real ESP32/ESP8266 node exists to test against directly).
- Everything downstream of that: Phase 2 (sensor state into the context frame), Phase 3
  (`climate_advisory`/`ambient_occupancy` rules) — correctly not started.

## Out of scope (per the task doc, unchanged)

- Autonomous actuation — not applicable regardless, no rule in `alfr3ddaemon.py` controls a
  device.
- ESPHome Phase 5 (push-based state), unless Phase 0 finds it's a hard prerequisite — moot until
  Phase 0 itself completes.
- Room-level presence trilateration (SA-8 Phase 3).
