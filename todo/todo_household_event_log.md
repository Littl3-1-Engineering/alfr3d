# SA-11: Durable Household Event Log

## Status: 🟢 Phase 1 + Phase 2 built and live-verified 2026-08-29; deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; `service-daemon`/
`service-api` rebuilt and redeployed; verified live with a clean cycle and a real authenticated
API response. See the top-level session note in this repo's Notion Capability Audit page for the
full deployment record (backup path, exact steps) shared across every item deployed that day.

Wave 1, item 1 of the situational-awareness expansion — foundational for SA-3, SA-10, SA-12,
and the revised SA-2. Everything on `event-stream` used to live only in `service_api`'s
in-memory `recent_events` (last 20, RAM-only) and `recent_sa` (current cycle only). Neither
survived a restart, so nothing downstream had real history to query.

**Phase 1** (`household_events` table, migration 0028): every message that lands in
`recent_events` also gets a durable INSERT via `_persist_household_events()` in
`service_api/app.py`'s `consume_events()`. The in-memory buffer and its WebSocket broadcast are
untouched — persistence is a parallel, best-effort destination; a DB error there is caught and
logged, never allowed to break the live feed. Retention: `prune_household_events()` in
`alfr3ddaemon.py`, scheduled on the same 6-hourly cadence as `compute_entity_baselines()`,
default 90 days (`HOUSEHOLD_EVENTS_RETENTION_DAYS`).

**Phase 2** (`subject_type`/`subject_id`/`verb`, migration 0029): nullable, additive columns.
Producers migrated so far, each its own commit:
- `service_device`: device-created event now carries `subject_type=device`, `subject_id=<new
  row id>`, `verb=created`.
- `service_user`: the two real presence-transition events (`user_online_*`/`user_offline_*` in
  `update_user_state()`) now carry `subject_type=user`, `subject_id=<user.id>`,
  `verb=came_online`/`went_offline`.
- Music: `now_playing_monitor.py`'s track-start/stop events and `alfr3ddaemon.py`'s
  `check_now_playing()` now carry `subject_type=track`, `subject_id=<spotify track id>`,
  `verb=play_start`/`play_stop`.
- Weather: `weather_util.py`'s `send_event()` gained optional `subject_type`/`subject_id`/`verb`
  kwargs; `speak_weather()`'s four muted-announcement call sites now pass
  `subject_type=weather`, `subject_id=<city name>`, `verb=muted_announcement`.
- Calendar: `calendar_utils.sync_calendar()` wipes and re-inserts its whole sync window on every
  run (no Google event id is stored to upsert against), so it now diffs against a `SELECT` of
  what was in `calendar_events` *before* the delete (keyed on
  `title, start_time, end_time, address, notes` as the same naive/second-precision datetime
  objects on both sides of the comparison, not the formatted strings passed to `INSERT`).
  `_publish_calendar_diff()` emits `subject_type=calendar_event`, `verb=created`/`removed` only
  for rows that actually appeared or disappeared — an unchanged, merely-re-synced event is not
  reported. 4 tests in `TestCalendarSync` (created / unchanged-is-silent / removed / the
  end_time-vs-start_time window regression below).

**Bug caught by live verification, fixed same session**: the sync window (both the DB `SELECT`
snapshot and the `DELETE`) originally filtered on `start_time >= now AND start_time <= future` —
mirroring the params sent to Google as `timeMin`/`timeMax`, but Google's API actually filters by
*end* time for `timeMin` and *start* time for `timeMax`, not `start_time` on both ends. A
real, currently-in-progress event ("Garbage sale", 12:00–18:00, caught mid-event at 15:37) kept
being returned by Google every sync, but its `start_time` (12:00) no longer satisfied
`>= now (15:37)` — so the `DELETE` stopped removing its old row (visible live as three
duplicate "Garbage sale" rows in `calendar_events` after three daemon restarts) *and* it fell
outside the diff's "before" snapshot, so every restart misreported it as newly `created`. Fixed
by filtering both queries on `end_time >= now AND start_time <= future` instead. Verified live:
two daemon restarts during the same still-ongoing event produced zero duplicate rows and zero
extra `calendar_event` publishes, vs. one duplicate row and one false "created" event per
restart before the fix.

**source_service inference**: `event-stream` messages carry no explicit producer identity today
(no `service` field, no Kafka headers) — `_infer_source_service()` in `service_api/app.py`
maps every current call site's `id` prefix to a service name, preferring an explicit `service`
key if a producer sets one. This is a heuristic, not a real field — worth promoting to an
explicit key on every producer if this table gets queried by source often.

## Live verification (2026-08-29, real docker-compose stack)

Ran `alembic upgrade head` against the live dev MySQL (was at 0023, six migrations behind —
including 0027 device_history partitioning, a different in-flight task, applied cleanly too),
rebuilt and recreated `service-api`/`service-daemon`/`service-device`/`service-user`/
`service-environment` with the new code, and let a real startup cycle run against real Kafka.

Confirmed:
- Every `event-stream` message produced exactly one `household_events` row (100 rows from ~4
  minutes of repeated startup cycles — `speak`/`daemon` sources, `personality_state` rows
  correctly stored with a `NULL` message, no drops, no duplicates).
- A live calendar sync produced a real `calendar_event`/`created` row for an actual Google
  Calendar event ("Garbage sale") end to end.
- `/api/events` still returns the same last-20 shape as before — 20 items, no wrapping, no
  dropped fields — confirming the in-memory buffer and dashboard feed are unaffected.
- `prune_household_events()` ran cleanly against the real table (0 rows pruned, correct cutoff
  computed: 90 days back from now).
- Found and fixed a real bug (see above) via two additional restarts during a still-in-progress
  calendar event — confirmed fixed, not a one-off.

## Not yet done

- **Row-growth measurement.** The 100-row/~4-minute number above is from repeated manual
  restarts (startup cycles are event-dense), not steady-state usage — not a real basis for
  tuning the 90-day default. Needs an actual multi-day run.
- **Phase 3 (SA cards into the log)** — persisting each published `situational-awareness` card
  as a `household_events` row (`subject_type=sa_card`) — not started. Explicitly optional/
  low-priority per the task doc; skip further if it delays anything SA-3/SA-10/SA-12 need.
- Remaining Phase 2 producers (email routine action, gathering-detected, setup/system-check
  events, `service_speak`'s TTS-failure/kafka-error events, `environment.py`'s location-change
  events) are still prose-only. Additive and nullable, so nothing is blocked on them — migrate
  opportunistically.

## Migration numbers

Raw SQL: `setup/migration_026_household_events.sql`,
`setup/migration_027_household_events_structured_fields.sql`. Alembic: `0028_household_events`,
`0029_household_events_structured_fields` (chain was at 0027 as of this session — note 0027
itself, `device_history` partitioning, was still uncommitted/in-flight from another task when
this one started).
