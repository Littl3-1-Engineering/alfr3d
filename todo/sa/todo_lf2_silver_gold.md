# LF-2: Silver and gold layers

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-2

## Status: 🟢 Deployed to the production NUC 2026-10-10 (migration 045 / alembic 0050). The first *scheduled* run (03:30 UTC) has not happened yet; the same function was run by hand and takes 13 s.

All 6 silver and 4 gold tables are built from bronze every night, after the bronze export, in
`service_sa/sa/silver.py`. Tables, columns and the reasoning behind every choice are in that
module's docstring; this doc records what the real data forced.

Silver fixes data quality once, so no rule or learner has to. Gold shapes silver for learners.
Both are rebuilt from bronze whenever their logic changes.

## Silver

- [x] **`presence_intervals`** (per user, all user types) -- *built from phone sightings only, see "What the real data changed"*; original plan: merge
  - arp-scan presence from `device_history` **timestamps only**. Its `state` column is backwards:
    the `before_device_update` trigger logs `OLD.state` (`createTables.sql:277`).
  - `household_events` `user/came_online|went_offline`
  - geofence `user/left_area|entered_area` (3 km radius; coarse fixes are clamped to 2 km
    accuracy, see [todo_device_location_reporting.md](todo_device_location_reporting.md))
  - Each interval carries `source` and `quality`. Per-device arp artifact rates (some devices'
    gaps are 100% artifacts, per [todo_departure_anomaly.md](todo_departure_anomaly.md)) feed
    `source_quality`. This also absorbs CEP's unbuilt "is the user home" merge rule.
- [x] **`device_sessions`**: on/off sessions derived from gaps, with the trailing-offline-gap quirk
      fixed.
- [x] **`sensor_15m`**: `smarthome_sensor_history` resampled to 15 min, with the sensor's identity
      stable across `smarthome_devices` id churn after a power-cycle (see
      [todo_esphome_situational_awareness.md](todo_esphome_situational_awareness.md)).
- [x] **`events_clean`**: `household_events` with exclusions applied and structured fields typed.
- [x] **`calendar_busy`**: per-user busy intervals from `calendar_events`.
- [~] **`day_context`** (built: dow, weekend, month, season, Ontario holidays; *daylight and a calendar-busy flag are not in it* -- busy intervals live in `calendar_busy`): dow, weekday/weekend, holiday, calendar-busy, daylight, season.
- [x] Every timestamp as both `ts_utc` and `ts_local`, from one timezone source
      (`get_env_timezone()`).
- [x] **`sa_data_exclusions`** (MySQL, hand-editable): `source`, `subject`, `start`, `end`,
      `reason`. Seed with the known test bursts (2026-09-16 03:02-03:04, 09-16/17, 10-01/02),
      device 60's self-pair volume `set` spam, and verification sessions.

## Gold

- [x] `presence_grid`: user × date × hour → minutes at home (not a fraction) plus an `observed` flag instead of a coverage ratio.
- [~] `daily_rhythm`: per user (*the household rows were not built; derive them from `presence_grid`*), first/last activity, departure/arrival, as hours.
- [x] `hourly_rates`: event counts per signal × date × hour.
- [x] `sensor_hourly`: per sensor × date × hour, weighted mean/min/max (not median: built from the 15-minute means).

## What the real data changed (Phase 0, 2026-10-10)

The plan assumed presence would be merged from arp-scan gaps, user events and geofence fixes.
Looking at the household's actual `device_history` first changed that:

- **Hardware is not presence.** The household already tags devices `resident`/`guest`
  (device_type 5/3) when they stand for a person (only phones carry these tags) and `HW` (2) for
  laptops, tablets, Kindles and speakers; that is what the tag is for. On 2026-10-09 Athos's phone was
  off the network 08:34-14:25 local while his laptop stayed on at home all day, so a union of his
  devices called him home. Silver builds presence from phones only; hardware feeds
  `device_sessions`. (Athos confirmed the tag's purpose mid-session.)
- **`state` is useless, `last_online` is the signal.** The trigger logs `OLD.state`, and two rows
  can share a second, so ordering-based fixes (`LEAD(state)`) are unstable. Presence uses the
  distinct `last_online` values, which are real sightings. A departure is the *last sighting*; the
  offline marking lags it by ~30 minutes.
- **The same phone has several device ids** (private-MAC rotation: `Littl3-Zen` x5, `Pixel-6a` x4),
  so presence is per user across all that user's phone ids.
- **No clean gap threshold.** Gaps between phone sightings decay smoothly through 30-60 minutes
  (a small bump at 29-33 min is the offline-marking threshold). `PRESENCE_GAP_MINUTES = 45` sits
  just past it and each interval carries `short_gaps_merged`, so a learner can see how much of it
  was inferred rather than observed.
- **User events and geofence were left out as sources.** `came_online`/`went_offline` are logged
  from the phone's state (confirmed by Athos 2026-10-10: user state is already logged by phone),
  so they are the same evidence as the phone sightings, not an independent source. Geofence has
  13 events from one person at 2 km accuracy. The `source` column is there so either can be added
  when it carries independent information.
- **The collector had a month-long outage.** `device_history` has *no rows at all* in June 2026 and
  ~38k in July (vs ~1M/month normally). A zero there is a missing measurement, not an absence, so
  the gold grids carry `observed` (the collector wrote at least 10% of its median hourly volume).
  For Athos: 0 of 720 hours observed in June, 31 of 744 in July, 598 of 744 in August.
- **Stale sightings exist.** Retired phones carry a `last_online` from 2023 into their first
  logged row (and into the current `device` snapshot). Sightings from before the collector started
  are dropped, with a one-hour tolerance because the first real sighting is logged in a row
  stamped just after it. Without this, one user's timeline started in 2023.
- **Sensor ids churn.** The ESPHome climate node came back after its 09-27 power-cycle as ids
  37893-37897 instead of 37885-37889. Silver resolves a stable `sensor_key`
  (`<node>:<sensor name>`) from the snapshots; for the retired ids, which exist in no snapshot,
  `sa_sensor_aliases` holds the mapping. **That mapping is inferred, not observed** (same order,
  +8 offset, matching row counts), and is marked as such in its `evidence` column. After
  aliasing, each of the five sensors is one continuous series 09-16 to 10-10.
- **Exclusions seeded only from what the todos already name**: the iot test bursts of 09-16,
  09-17, 10-01 and 10-02 (54 events). Bursts on 10-06 00:54 and 10-08 01:16 were *not* excluded:
  nothing documents them as tests, so they stay until someone says otherwise.
- **Calendar titles and notes stay in bronze.** `calendar_busy` keeps only the busy interval and
  three flags.

## Result, on the real lake

Build takes 8 s (13 s with the bronze export); silver is 968 KB and gold 152 KB. It answers the
question that started this: Athos's weekday 09:00-17:00 `P(home)` averages 0.72-0.79. Of the ten
Fridays before today, five were exactly 1.00 and eight were 0.84 or higher (0.72 on 09-18); today,
2026-10-09, scores **0.32**, the lowest since August. One earlier Friday, 2026-05-08, also scores
0.00, but that is in May when the collector was only partly running (278 of 707 hours observed),
so it may be a gap in collection and not a real absence. The weekday series is also falling: 1.00,
0.77, 0.74, 0.48, 0.32 over the last five weekdays, a trend and not a one-off. A learner that averages by weekday would miss that; recency weighting and
drift detection (LF-3, LF-5) are what catch it.

## Verify

- [x] 26 tests in `tests/test_sa_silver.py` on a synthetic lake: phones vs hardware, rotated ids,
      short-gap counting, snapshot sightings, system/catch-all users excluded, stale sightings,
      DST (EST vs EDT), exclusion narrowing, alias resolution, calendar privacy, holidays,
      zero-filled grids, `observed`, idempotent rebuild, missing inputs.
- [x] Migration 045: backup `alfr3d_backup_20261009_213442_pre_0050.sql.gz`, rehearsed on a
      restored copy (up, down, up), then production.
- [x] Real-data check above, including the 2026-10-09 Friday.
- [ ] Not yet observed: the scheduled 03:30 UTC run.

## Known limits / follow-ups

- **Daylight** (sunrise/sunset per day) is not in `day_context`; it needs the latitude/longitude
  and a sunrise calculation. Add when a learner wants it.
- Interval ends are the last sighting, so they run ~1 minute short of true departure.
- A user deleted from MySQL drops out of `persons` and so out of presence; their history is still
  in bronze.
- `device_sessions` and `presence_intervals` use the same 45-minute gap. Hardware that is
  silent for 45 minutes (a sleeping laptop) is a new session, which is right for rhythm learners.
- `OBSERVED_MIN_FRACTION` (10% of median) and `PRESENCE_GAP_MINUTES` are judgement calls, named
  constants at the top of `silver.py`.
- The two iot bursts on 10-06 00:54 and 10-08 01:16 are candidates for `sa_data_exclusions` if
  anyone recognises them as tests.
