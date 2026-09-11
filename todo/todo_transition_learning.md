# SA-12: Transition learning & anticipation/surprise

## Status: 🔴 SA-12 still stopped — but for a different reason than Aug 30

- **2026-08-30:** stopped at Phase 0 because SA-11 had only ~10 hours of runtime.
- **2026-09-07 (Phase 0b re-check, real production DB):** elapsed time is no longer the
  blocker — `household_events` now spans **8.98 real days** with steady daily structured
  output. The blocker is now purely **structural**: every candidate transition pair the task
  doc names (device state changes, routine triggers, presence→device) has **exactly zero**
  structured rows, because no producer emits them. **Verdict: Branch C** — do not build
  Phase 1; add the two missing producers so future Phase 0 re-checks are meaningful, then
  keep SA-12 stopped. See the Phase 0b section below.

Last item of the roadmap, Wave 4, explicitly gated on SA-11 (durable household event log)
accumulating real history. The task doc's own Phase 0 instruction is direct: *"Confirm SA-11 has
been live long enough to have real transitions to mine... don't scope this against hypothetical
data."*

## Phase 0 — investigate

Checked directly against this session's real `household_events` data (the same table SA-11
built earlier in this session), not assumed:

- **`household_events` spans barely 10 hours of real history**: earliest row
  `2026-08-29 15:35:40`, latest `2026-08-30 01:56:54` — SA-11 landed *earlier in this same
  session*, so this is genuinely all the runtime it has had, not a stale measurement.
- **Only 71 rows carry the structured `subject_type`/`verb` fields this whole feature depends
  on** (out of 1,217 total rows — most rows are still prose-only from producers SA-11 hasn't
  migrated to structured fields yet). Breakdown: `track/play_start` (57 — the overwhelming
  majority, dominated by whatever was playing during this session's own verification work),
  `user/went_offline` (5), `user/came_online` (5), `calendar_event/created` (2),
  `track/play_stop` (2). No device-to-device transitions, no presence-to-routine transitions —
  none of the task doc's own named candidate pairs (device-to-device, presence-to-device,
  calendar-to-device) have more than a handful of samples, and most have zero.
- Every downstream Phase 0 question the task doc asks (what transition window is empirically
  right, which candidate pairs are worth mining, whether the 6-hourly cadence has headroom for a
  second pass) is unanswerable honestly against 10 hours and 71 structured rows — any number
  picked now would be invented, not derived, which is exactly what this Phase 0 exists to
  prevent.

**Verdict: stop here.** Not a feasibility failure like SA-8, not an environment blocker like
SA-9 — the mechanism this item would build is sound and the task doc's own design (conditional
frequency counts, no ML, the same `entity_baselines`-style sample floor) is well-reasoned. It
simply has no real data to learn from yet. Building `event_transitions`/`compute_transitions()`/
`check_anticipation`/`check_surprise` against 71 rows spanning half a day would produce
confidence values with no statistical meaning, the same anti-pattern (fabricated-looking output
from insufficient data) this entire SA initiative has repeatedly refused to ship.

## Phase 0b — re-check (2026-09-07)

Run against the **production** database (real NUC `alfr3d-mysql-1`, `alfr3d_db`), not the dev
mirror. Raw query output, verbatim:

```
-- volume + time span
+------------+---------------------+---------------------+------------+-----------+
| total_rows | earliest            | latest              | span_hours | span_days |
+------------+---------------------+---------------------+------------+-----------+
|      14846 | 2026-08-30 02:48:32 | 2026-09-08 02:19:47 |        215 |         8 |
+------------+---------------------+---------------------+------------+-----------+
-- span_days, precise: 8.98

-- structured rows (subject_type AND verb both set)
+-----------------+
| structured_rows |
+-----------------+
|            1947 |   (of which only 247 are NOT track/play_start)
+-----------------+

-- full subject_type / verb breakdown (all rows with either field set)
+----------------+--------------------+------+---------------------+---------------------+
| subject_type   | verb               | n    | first_seen          | last_seen           |
+----------------+--------------------+------+---------------------+---------------------+
| track          | play_start         | 1700 | 2026-08-30 02:51:35 | 2026-09-08 02:18:13 |
| user           | went_offline       |   69 | 2026-08-30 12:35:44 | 2026-09-07 23:15:18 |
| user           | came_online        |   67 | 2026-08-30 15:51:12 | 2026-09-08 01:59:19 |
| track          | play_stop          |   61 | 2026-08-30 02:51:45 | 2026-09-08 02:19:47 |
| weather        | muted_announcement |   46 | 2026-08-30 02:48:32 | 2026-09-07 07:32:13 |
| device         | created            |    3 | 2026-09-02 02:21:53 | 2026-09-03 22:20:00 |
| calendar_event | removed            |    1 | 2026-08-31 17:29:52 | 2026-08-31 17:29:52 |
+----------------+--------------------+------+---------------------+---------------------+

-- targeted check: any row for a device state change / routine execution / presence pair?
--   subject_type IN (routine, scene, presence)
--   OR verb IN (turned_on, turned_off, toggled, set, executed, on, off)
Empty set.  ← zero rows

-- structured rows per day (shows steady, ongoing production — not a one-session artifact)
2026-08-30:228  08-31:298  09-01:315  09-02:289  09-03:209
09-04:127  09-05:54  09-06:135  09-07:260  09-08:34 (partial)
```

Codebase grep (`subject_type` / `verb` string literals across `services/`, `common/`)
confirms the producer list in the task doc is still exhaustive and unchanged:

| producer file | subject_type | verb(s) |
|---|---|---|
| `service_daemon/utils/now_playing_monitor.py`, `alfr3ddaemon.py` | `track` | `play_start`, `play_stop` |
| `service_user/app.py` | `user` | `came_online`, `went_offline` |
| `service_daemon/utils/calendar_utils.py` | `calendar_event` | `created`, `removed` |
| `service_device/app.py` | `device` | `created` (lifecycle only — NOT state toggles) |
| `service_environment/weather_util.py` | `weather` | `muted_announcement` |

**Verdict: Branch C.** Elapsed time is now genuine (9 days vs. 10 hours on Aug 30) and
structured events are being produced every day, so the Aug 30 time-runway blocker is cleared.
But *every* candidate transition pair this feature would mine is structurally absent:

- **device state changes** (on/off/toggle/set): 0 rows. The only `device` events are 3
  lifecycle `created` rows. `control_iot_device()` in `service_api/routes/iot.py` emits
  nothing to the event stream on a successful command.
- **routine executions**: 0 rows. Neither the daemon's scheduled `check_routines()` nor the
  API's `run_routine()` emits a structured event when a routine fires.
- **presence→device**: impossible to observe without the device events above; presence data
  itself is healthy (136 `user` came/went rows over 9 days).

Branch A (stop, build nothing) was rejected because the blocker is *no longer* "not enough
time" — it is a specific, fixable gap in producer coverage, which is exactly what Branch C
exists to close. Branch B was rejected because there is no candidate-pair data at all, in any
volume.

## Phase 0b follow-up work (Branch C) — producer instrumentation, 2026-09-07

Added two new structured-event producers. **No new write path** — both reuse the existing
`get_producer().send("event-stream", {...})` → `service_api._persist_household_events()` →
`household_events` path that every other structured producer already uses (SA-11). The event
dicts set `"service"` explicitly so `_infer_source_service()` labels them without needing a new
`id`-prefix entry.

1. **`subject_type="device"` / `verb` ∈ {`turned_on`, `turned_off`, `toggled`, `set`}** —
   `services/service_api/routes/iot.py`. New module-level helper `_emit_device_event()`;
   called from each of the three `if success:` branches (Home Assistant, ESPHome,
   SmartThings) in `control_iot_device()`, i.e. only after the command actually succeeds.
   Command→verb map: `turn_on`→`turned_on`, `turn_off`→`turned_off`, `toggle`→`toggled`,
   everything else (brightness/temperature/mode/position/lock/media/volume/…)→`set`.
   `subject_id` = the `smarthome_devices.id`.
2. **`subject_type="routine"` / `verb="executed"`** — emitted at the moment a routine fires:
   - `services/service_daemon/utils/util_routines.py` `check_routines()` — the scheduled +
     event-triggered execution point, right after `should_trigger` and the condition check
     pass, before `execute_actions()`.
   - `services/service_api/routes/routines.py` `run_routine()` — the manual "run now" API
     path.
   `subject_id` = the `routines.id`.

SA-12 itself **stays stopped**. This sub-phase only makes future Phase 0 re-checks meaningful.
No `event_transitions` table, no `compute_transitions()`, no anticipation/surprise code was
written.

### Live verification (2026-09-08, deployed as commit `b9e6e36f`)

Deployed to the NUC: `docker compose up -d --build service-api service-daemon` (both came up
clean, `_emit_device_event` / `_emit_routine_executed` confirmed present in the running
containers).

- **routine (manual): ✅ VERIFIED end-to-end.** `POST /api/routines/2/run` produced
  `household_events` row 14917: `source_service='api'`, `subject_type='routine'`,
  `subject_id='2'`, `verb='executed'`, message `routine 'Morning' executed (manual run)`.
  The `event-stream` → `_persist_household_events()` path logged the event and wrote the row.
- **routine (scheduled): ⏳ pending** — no daemon fire yet (next Sunrise/Morning/Sunset/Bedtime
  will produce a `routine`/`executed` row with `source_service='daemon'`). Same helper, same
  path as the verified manual case; low risk.
- **device event: ⚠️ BLOCKED — not by SA-12 code, by a Home Assistant outage.**
  `POST /api/iot/devices/60/control` returns HTTP 500 because **every** HA-sourced device is
  offline (`SELECT source, online, COUNT(*)` → `('homeassistant', 0, 61)`, zero rows with
  `online=1`). The HA bridge is fully disconnected on production, so no control command can
  reach `if success:` and `_emit_device_event` never fires. `_emit_device_event` itself is
  unexercised. It is byte-for-byte the same emit → persist mechanism the routine helper just
  proved, so confidence is high, but it has no live row yet. Re-verify once HA is reconnected
  (separate issue — see the dev-DB HA-disconnected note; it now affects production too) via a
  real successful control command. A direct `from routes.iot import _emit_device_event;
  _emit_device_event(60, "media_player", "volume_set", "verify")` call inside the running
  `service-api` container was tried 2026-09-08 and produced **no** row and no consumer log
  line — a fresh `docker exec python` process builds its own Kafka producer whose `send`/
  `flush` didn't deliver before the process exited; not a reliable verification path. Exercise
  it through the real HTTP route instead.

### Re-check reminder: **~2026-09-28** (≈3 weeks out)

Re-run the Phase 0b queries. Proceed to Phase 1 only if device-state and/or routine-executed
rows have accumulated real multi-week history with genuine candidate pairs (e.g. a recurring
presence→device or routine→device sequence). Derive every threshold/window from that real
data — do not invent one.

## Data points collected for SA-12

SA-12 builds no store of its own yet. Its raw material is the **structured subset** of
SA-11's `household_events` table — rows where **both `subject_type` and `verb` are set**.
A future `compute_transitions()` orders these by `occurred_at` and counts which
`(subject_type, verb)` follows which within a transition window. Everything below is what
is being accumulated toward that.

### Per-row schema (`household_events`, migrations 026 + 027)

| column | type | role for SA-12 |
|---|---|---|
| `id` | BIGINT UNSIGNED PK | row identity |
| `occurred_at` | DATETIME | **ordering key** — defines "A then B" and the transition window |
| `event_type` | VARCHAR(32) | loose type string mirrored from the event-stream message |
| `source_service` | VARCHAR(32) | producing service (`_infer_source_service()`, or explicit `service` key) |
| `message` | TEXT NULL | prose; not queried for transitions |
| `subject_type` | VARCHAR(32) NULL | **structured** — the entity category (the "what") |
| `subject_id` | VARCHAR(64) NULL | **structured** — the specific entity id |
| `verb` | VARCHAR(32) NULL | **structured** — the action |

Index: `idx_household_events_type_occurred (event_type, occurred_at)`.

### Structured streams currently produced

Inherited from SA-11 Phase 2:

| subject_type | verb(s) | subject_id | producer(s) |
|---|---|---|---|
| `track` | `play_start`, `play_stop` | Spotify track id | `service_daemon/utils/now_playing_monitor.py`, `alfr3ddaemon.py` `check_now_playing()` |
| `user` | `came_online`, `went_offline` | `users.id` | `service_user/app.py` `update_user_state()` |
| `calendar_event` | `created`, `removed` | — (none stored) | `service_daemon/utils/calendar_utils.py` `_publish_calendar_diff()` |
| `device` | `created` (lifecycle only — **not** state changes) | new `smarthome_devices.id` | `service_device/app.py` |
| `weather` | `muted_announcement` | city name | `service_environment/weather_util.py` `speak_weather()` |

Added for SA-12 (Branch C, 2026-09-07, commit `b9e6e36f`) — reuse the existing
`get_producer().send("event-stream", …)` → `service_api._persist_household_events()` path,
`"service"` set explicitly on the event dict:

| subject_type | verb(s) | subject_id | producer(s) | notes |
|---|---|---|---|---|
| `device` | `turned_on`, `turned_off`, `toggled`, `set` | `smarthome_devices.id` | `service_api/routes/iot.py` `_emit_device_event()`, called from each `if success:` branch (Home Assistant / ESPHome / SmartThings) of `control_iot_device()` | command→verb: `turn_on`→`turned_on`, `turn_off`→`turned_off`, `toggle`→`toggled`, everything else (brightness/temp/mode/position/lock/media/volume/…)→`set`. Emitted **only** after the command actually succeeds. |
| `routine` | `executed` | `routines.id` | `service_daemon/utils/util_routines.py` `check_routines()` (scheduled + event-triggered, after `should_trigger` + condition check, before `execute_actions()`); `service_api/routes/routines.py` `run_routine()` (manual "run now") | `source_service` is `daemon` for scheduled fires, `api` for manual runs |

Added 2026-09-11 — the geofence follow-up [[todo_device_location_reporting]]'s "Deferred" section
named, built directly on top of that pipeline rather than real OS geofencing (no background-
location permission, matching that feature's coarse/foreground-only design decision):

| subject_type | verb(s) | subject_id | producer(s) | notes |
|---|---|---|---|---|
| `user` | `left_area`, `entered_area` | `users.id` | `service_api/routes/context.py` `_emit_geofence_transition_events()`, called from `report_device_location()` (`POST /api/context/device-location`) after each accepted batch commits | Backend-side, not client geofencing: compares each newly-accepted fix's distance from the household's `environment` coordinates against a 300m radius, using `distance ± accuracy_m` to only classify a fix as confidently home/away (ambiguous fixes don't move the state, so poor-accuracy "network" fixes near the boundary can't cause flapping). Tracked per `client_install_id`, not merged across a user's devices — matches `device_location_history`'s own per-device design, so one device leaving while another stays home reports as that device's own transition. Code + unit tests only as of 2026-09-11 — **not yet deployed** (no migration needed, it's a pure route addition) and not yet live-verified against a real departure/arrival. |

### Collection status (as of 2026-09-08, geofence producer added 2026-09-11)

| stream | live rows accumulating? |
|---|---|
| `track/play_*` | yes — dominant volume (1700 `play_start` over 9 days) |
| `user/came_online`, `user/went_offline` | yes — healthy (~136 rows / 9 days) |
| `weather/muted_announcement` | yes — 46 rows |
| `calendar_event/created`, `/removed` | trickle — 1–2 rows total |
| `device/created` | trickle — 3 rows (lifecycle only, useless for transitions) |
| `routine/executed` (manual) | ✅ verified end-to-end (row 14917) |
| `routine/executed` (scheduled) | ⏳ deployed, awaiting first daemon fire |
| `device/turned_on|off|toggled|set` | ⚠️ deployed but **near-zero rows**, structurally. The household moved; ~59 HA entities (Google Homes / TVs / tablets) stayed at the old place — some may be recovered, most won't. Only `Moonrise TV` (+`moonrise_tv_2`) followed, so the device-transition stream has ~one controllable device and stays too thin for SA-12 until the new house accumulates real smart devices. (2026-09-08 fixes: `93354114` corrected `sync_ha_devices()`'s `online = state == "on"` bug; an auto-prune `3b10fadb` was tried then reverted `85e6be17` as too aggressive/FK-unsafe; `3dfa3f29` added `DELETE /api/iot/devices/{id}` for deliberate removal instead.) |
| `user/left_area`, `user/entered_area` | 🆕 not deployed yet — code + unit tests only (2026-09-11). Once live, this is the **presence** half of the presence→device/routine candidate pairs; depends on the household actually having `device-location` reporting toggled on (Deck Settings, default OFF) and real deck↔backend traffic — same opt-in gate as the rest of [[todo_device_location_reporting]]. |

Candidate transition pairs the task doc names — presence→device, routine→device,
device→device — have **zero** samples until the two Branch C streams (and now the geofence
producer above, once deployed and opted into) accumulate real history. That is what the
~2026-09-28 re-check measures.

## Not yet done

- Everything: Phase 1 (`event_transitions` table, `compute_transitions()`), Phase 2
  (`check_anticipation`/`check_surprise`), Phase 3 (decay, explicitly deferred by the task doc
  regardless). None of this should start until SA-11 has accumulated real weeks-to-months of
  structured event history, the same "genuine data runway" precedent SA-2's attention telemetry
  and SA-3's departure baselines both needed before they meant anything.
- **A concrete re-open condition, not just "wait and see"**: revisit once `household_events` has
  (a) enough elapsed real time (weeks, not hours — matching the order of magnitude SA-3/SA-10
  needed for their own day-bucketed baselines) and (b) SA-11 Phase 2's structured `subject_type`/
  `verb` migration has been extended to more producers than the handful populated today (device
  state changes and calendar events barely appear; the candidate pairs this feature needs mostly
  don't exist as structured rows yet, independent of the time-span question).

## Out of scope (per the task doc, unchanged)

- Any regression, neural, or black-box model — moot, nothing was built.
- Cross-household pattern sharing — moot.
- Recency decay (Phase 3) — explicitly deferred by the task doc regardless of this Phase 0
  outcome.
- Any autonomous action on a high-confidence prediction — moot.
