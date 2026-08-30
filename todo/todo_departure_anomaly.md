# SA-3: Presence-transition spike & departure anomaly

## Status: 🟢 Built and live-verified 2026-08-29 (no live *firing* observed yet -- see below);
deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; `service-daemon`
rebuilt and redeployed; verified live with a clean cycle and a real authenticated API response.
The real baselines this needs are now computing against the household's actual production
history (not just the local dev stack's mirrored copy) -- the still-open "no live firing" item
below is the same, just now on the box that actually matters.

Last item of Wave 2, following [[todo_context_frame]] (SA-4) and [[todo_structured_card_payload]]
(SA-5), unblocked by [[todo_household_event_log]] (SA-11) landing earlier this session. Unlike
every prior item, this one is explicitly spike-first: the task doc's own premise ("departure-
anomaly detection needs a new `user_history` table and a ~2-week data lead time") was flagged as
untested and had to be verified against live data before any code landed.

## Phase 0 — the spike (real data, not schema)

Investigated directly against the running stack's `device_history` (1.48M rows, six months of
history) and the arp-scan sync code (`services/service_device/app.py`), not assumptions:

- **Write frequency**: every ~60-90s while a claimed device is actually seen (`Device.update()`
  fires an unconditional `UPDATE` on every arp-scan hit), plus exactly one write when
  `check_offline_devices()` bulk-flips a stale device (`last_online` > 30 min old) to offline.
  So `device_history` *is* derivable as a transition log, but only via the **gaps between
  consecutive writes**, not the row's own `state` column.
- **A real, non-obvious gotcha found by reading the trigger, not the docs**:
  `before_device_update` is a `BEFORE UPDATE` trigger that logs `OLD.state` -- the value from
  *before* the write that's happening right now. A routine "still online" ping and the
  offline-flip event both log `state=online` (2); only a reconnect-after-absence row logs
  `state=offline` (1). Treating the raw column as "the state at that timestamp" is backwards.
  This also means `compute_entity_baselines()`'s existing device on/off-session reconstruction
  (pre-dating this task) likely measures "online duration + the following offline gap" as one
  lumped number, not pure on-duration -- a pre-existing quirk, out of scope to fix here, but
  worth flagging since it wasn't previously documented anywhere.
- **Retention depth**: 1,484,204 rows spanning 2026-02-25 to 2026-08-29 (~185 days), matching
  `createTables.sql`'s `cleanup_device_history_event` (`DELETE ... INTERVAL 180 DAY`). Ample --
  the task doc's feared "~2-week lead time" doesn't apply; the history already exists today.
- **False-departure rate (WiFi power-saving)**: measured directly via gap-length distributions
  on real claimed devices, not assumed. A continuously-tracked device (the owner's tablet,
  device_id 64) had 28 offline episodes over 6 months: only 1 was a short 31-90 min blip, 24
  were genuine multi-hour absences. But some claimed devices (`Vanja_Honor`, `Jenna`'s
  `Zenfone10`) showed **100% of their gaps as tracking artifacts** -- essentially never
  continuously pinged, only sporadically detected. Per-device reliability varies enormously.
  **Resolution**: aggregate at the per-*user* level (union of every claimed device), the same
  level `context_frame.fetch_online_devices()` already uses for household composition --
  a person with one flaky secondary device and one reliable primary device still reads
  correctly as "home" the whole time.
- **A second real noise source, found only by running the actual extraction**: even after
  per-user aggregation, a naive "first gap of the calendar day" reading produced an implausibly
  scattered distribution (a test extraction for one resident: weekday hours from 1am to 10pm,
  median "3pm"). Root cause: without an anchor, a day's first-seen row can be a late reappearance
  of an absence that started the *previous* night, misattributing one real departure to every
  day it spans. Fixed by requiring a resident be seen online in the 02:00-05:00 local window
  before that day counts at all (`_departure_hours_by_bucket()`'s "confirmed home overnight"
  check) -- this alone took a resident's real weekday sample from wildly scattered to a
  recognizable cluster (still real evidence that per-user departure timing is inherently noisier
  than device rhythm ever was -- see the sample-count/spread guards below).
- **Claimed-device coverage**: 4 non-guest users (`Munja`, `Vanja`, `Jenna`, `athos`) hold
  claimed devices with real history. Most other claimed devices in this household belong to
  `guest`-typed users (`Predrag`, `Elenka`, `Gorango`, etc.) and are correctly out of scope --
  reused the existing `ut.type IN ('owner', 'technoking', 'resident')` convention already
  established in `services/common/db_utils.py`'s "worthy listeners" check, rather than inventing
  a new guest filter.

**Verdict: Green, derive from `device_history`, no new table** -- with two load-bearing
refinements the naive reading of the task doc wouldn't have surfaced: (1) per-user aggregation
across claimed devices, not per-device, and (2) an overnight-confirmation anchor plus a
reliability floor on both sample count *and* observed-hour spread, not sample count alone.

## Phase 1 — schema and per-user baseline

Migration 0033 (`migration_031_departure_anomaly.sql`): extends `entity_baselines`
(migration 023) rather than a parallel table, per the task doc's own instruction --
`entity_type` gains `'user'`, and a new `day_bucket` (`'all'`/`'weekday'`/`'weekend'`) column
joins the unique key (existing `device`/`smarthome_device` rows default to `'all'`, unchanged).
No new numeric columns: `'user'` rows reuse the existing generic FLOAT/TINYINT columns with a
documented different meaning (`typical_active_hour` = typical first-departure hour,
`typical_daily_min`/`max` = earliest/latest observed departure hour -- the "spread" the task doc
asked for; `median_on_minutes` stays NULL, on-duration doesn't apply here).

`_departure_hours_by_bucket()` (new, alongside `compute_entity_baselines()`): reduces one
resident's raw device_history timestamps (union of every claimed device) into
`{"weekday": [hour, ...], "weekend": [hour, ...]}`, using the gap+anchor method above, not the
state column. `compute_entity_baselines()` (same function, same 6-hourly schedule, extended
rather than duplicated) now also loops eligible residents, builds their combined device_history
timestamp list (converted to local time via `db_utils.get_env_timezone()`, matching the rest of
this file's local-time convention), and upserts a baseline row per bucket once
`DEPARTURE_BASELINE_MIN_SAMPLES` (8) is cleared.

`DEPARTURE_BASELINE_LOOKBACK_DAYS` was set to **120, not the original 60**, after measuring both
against this household's real history: 60 days left every resident under the sample floor; 120
was the first window where multiple residents actually cleared it (see Live verification). 180
would exactly match `device_history`'s own retention ceiling, leaving no cushion before rows the
window depends on get pruned daily.

## Phase 2 — `check_departure_anomaly` rule

New `DISPLAY_RULES` entry, priority 2.7 (directly below `rhythm_break_anomaly`'s 2.6, its human
analogue, per the task doc's own suggested placement). Fires only when, for at least one
resident: a baseline exists for today's weekday/weekend bucket clearing both
`DEPARTURE_BASELINE_MIN_SAMPLES` *and* `DEPARTURE_BASELINE_MAX_SPREAD_HOURS` (4h -- see Live
verification for why this second gate turned out to matter in practice, not just in theory); the
local hour is past that baseline's typical hour plus `DEPARTURE_ANOMALY_GRACE_HOURS` (1.5); at
least one claimed device is online right now; and no `calendar_events` row covers this exact
moment (`start_time <= now <= end_time`, checked directly -- `frame.upcoming_events` only looks
~2 hours *forward* and would miss an already-in-progress WFH block). Only the single most-overdue
resident's card is returned per cycle, same "one card, most-overdue wins" precedent as
`check_rhythm_break_anomaly()`. `entity_name` (the resident's username) drives suppression's
subject key (`CARD_SUBJECT_KEY_EXTRACTORS`), same reasoning as rhythm_break_anomaly: dismissing
one resident's card must not suppress a different resident's.

Tone constraint from the task doc, held to literally: `content` reads
`"{username} still home — unusual for a {day_of_week}"` -- an ambient observation, never a
welfare-check phrasing.

## Testing

New: `TestDepartureHoursByBucket` (5 tests -- the gap/anchor reduction itself: records the right
departure hour, skips a day with no overnight confirmation, ignores a sub-threshold blip,
handles fewer than 2 timestamps, aggregates a week into the right buckets).
`TestComputeUserDepartureBaselines` (3 tests -- a bucket that clears the floor gets upserted
while one that doesn't is skipped in the same pass, the eligible-residents query text scopes to
non-guest types, a user with zero claimed devices is skipped cleanly).
`TestCheckDepartureAnomaly` (8 tests -- fires when every condition holds; no candidates; not yet
past the grace window (and confirms the online-status query is never reached for a skipped
candidate); resident not home; a calendar event covers now; picks the most-overdue of several
qualifying residents; no DB connection attempted at all when frame lacks `local_dt`/`day_mood`;
DB error handling). Two pre-existing `TestComputeEntityBaselines` tests and the two
`TestDecideDisplays`/`TestCardSuppression` "everything fires" end-to-end tests were updated for
the new call sequence and the 17th registered rule. Full suite: **424 passed, 9 skipped**
(MySQL-integration skips, unrelated), lint clean.

## Live verification (2026-08-29 -> 2026-08-30, real docker-compose stack)

- Migration 0033 applied cleanly against the real DB (`docker compose --profile test run --rm
  migrate`); confirmed via `DESCRIBE`/`SHOW INDEX` that `entity_type` gained `'user'` and
  `day_bucket` joined the unique key exactly as designed.
- Rebuilt/redeployed `service-daemon`; a full cycle logged `checking departure_anomaly` with no
  errors, correctly returning nothing before any baseline existed.
- Manually invoked `compute_entity_baselines()` against real data (rather than waiting for the
  6-hour schedule) at the original `DEPARTURE_BASELINE_LOOKBACK_DAYS = 60`: **zero residents
  cleared the 8-sample floor** (`Jenna: {weekday: 3, weekend: 2}`, `Munja: {weekday: 2, weekend:
  2}`, `athos: {weekday: 3, weekend: 1}`, `Vanja: {weekday: 0, weekend: 0}`) -- a real, honest
  finding that 60 days was too short given how strict the overnight-confirmation anchor is.
  Re-measured at 120 and 180 days before picking a value (see table below); redeployed with
  `DEPARTURE_BASELINE_LOOKBACK_DAYS = 120` and re-ran:

  | lookback | Jenna wd/we | Munja wd/we | athos wd/we | Vanja wd/we |
  |---|---|---|---|---|
  | 60d | 3 / 2 | 2 / 2 | 3 / 1 | 0 / 0 |
  | 120d | 12 / 5 | 10 / 2 | 6 / 10 | 0 / 0 |
  | 180d | 55 / 21 | 38 / 10 | 23 / 52 | 0 / 0 |

  At 120 days, three baselines cleared the sample floor and were upserted into
  `entity_baselines`: `athos`/weekend (10 samples, hour range 4-4, spread **0**), `Jenna`/weekday
  (12 samples, range 3-17, spread 14), `Munja`/weekday (10 samples, range 2-17, spread 15).
  **The spread guard (`DEPARTURE_BASELINE_MAX_SPREAD_HOURS = 4`) then correctly rejected the
  latter two at query time** -- their real departure-hour history is genuinely scattered (not a
  bug, this is exactly the Phase 0 noise finding), leaving only `athos`/weekend as a baseline
  `check_departure_anomaly()` would actually act on. This is the two-gate design (sample count
  *and* spread) working as intended against real data, not a hypothetical: without the spread
  gate, Jenna's and Munja's noisy weekday history would have produced false-alarm-prone cards.
  `Vanja` never got a baseline at all (0 samples in every window) -- consistent with the Phase 0
  finding that her claimed devices show unreliable continuous tracking; correctly silent rather
  than fabricating a baseline from data that isn't there.
- A subsequent full cycle logged `checking departure_anomaly` again with no errors, correctly
  returning no card: `athos`'s devices were confirmed offline at check time (a live
  `SELECT ... WHERE u.username = 'athos'` showed every claimed device `offline`), so the
  "resident currently home" gate correctly withheld the card -- a real, live confirmation that
  this gate prevents a false positive, not just a unit-test fabrication.

## Not yet done

- **A live firing has not been observed.** The one baseline that clears both gates today
  (`athos`/weekend) needs athos to actually be home, past 05:30 local, on a Saturday or Sunday,
  with no covering calendar event, to produce a real card -- that combination hasn't occurred
  during this verification window. Same category of gap as SA-4's `empty_house_still_on` (also
  never observed firing live) and SA-7's conferencing metadata (never observed against a real
  conferencing event) -- the rule's logic is covered by 8 direct unit tests plus the live
  computation above; a genuine end-to-end firing is still open.
- **`Vanja` and most weekday baselines remain unreliable** at the current lookback/anchor/spread
  settings -- this is accepted as correct, conservative behavior per the task doc's own accepted
  "ship with the card off by default rather than something that cries wolf" outcome, not a bug to
  chase down further this pass.
- The pre-existing `compute_entity_baselines()` device on/off-session quirk found during the
  Phase 0 spike (measuring "on-duration + trailing gap" rather than pure on-duration, due to the
  same `before_device_update` trigger semantics) was flagged but not fixed -- out of scope for
  this task, belongs with `todo/todo_rhythm_break_anomaly.md` if ever revisited.

## Out of scope (per the task doc, unchanged)

- Cross-user correlation ("everyone's late") -- that's weather/traffic-driven, see SA-10.
- Any escalation beyond a card: no push, no speak, no notification.
- Guest-type users.
