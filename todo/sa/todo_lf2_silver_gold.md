# LF-2: Silver and gold layers

> **Layer:** data · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-2

## Status: 🔲 Not started (planned 2026-10-09). Depends on LF-1b.

Silver fixes data quality once, so no rule or learner has to. Gold shapes silver for learners.
Both are rebuilt from bronze whenever their logic changes.

## Silver

- [ ] **`presence_intervals`** (per user, all user types): merge
  - arp-scan presence from `device_history` **timestamps only**. Its `state` column is backwards:
    the `before_device_update` trigger logs `OLD.state` (`createTables.sql:277`).
  - `household_events` `user/came_online|went_offline`
  - geofence `user/left_area|entered_area` (3 km radius; coarse fixes are clamped to 2 km
    accuracy, see [todo_device_location_reporting.md](todo_device_location_reporting.md))
  - Each interval carries `source` and `quality`. Per-device arp artifact rates (some devices'
    gaps are 100% artifacts, per [todo_departure_anomaly.md](todo_departure_anomaly.md)) feed
    `source_quality`. This also absorbs CEP's unbuilt "is the user home" merge rule.
- [ ] **`device_sessions`**: on/off sessions derived from gaps, with the trailing-offline-gap quirk
      fixed.
- [ ] **`sensor_15m`**: `smarthome_sensor_history` resampled to 15 min, with the sensor's identity
      stable across `smarthome_devices` id churn after a power-cycle (see
      [todo_esphome_situational_awareness.md](todo_esphome_situational_awareness.md)).
- [ ] **`events_clean`**: `household_events` with exclusions applied and structured fields typed.
- [ ] **`calendar_busy`**: per-user busy intervals from `calendar_events`.
- [ ] **`day_context`**: dow, weekday/weekend, holiday, calendar-busy, daylight, season.
- [ ] Every timestamp as both `ts_utc` and `ts_local`, from one timezone source
      (`get_env_timezone()`).
- [ ] **`sa_data_exclusions`** (MySQL, hand-editable): `source`, `subject`, `start`, `end`,
      `reason`. Seed with the known test bursts (2026-09-16 03:02-03:04, 09-16/17, 10-01/02),
      device 60's self-pair volume `set` spam, and verification sessions.

## Gold

- [ ] `presence_grid`: user × date × hour → fraction of the hour at home, plus coverage.
- [ ] `daily_rhythm`: per user and household, first/last activity, departure/arrival, as hours.
- [ ] `hourly_rates`: event counts per signal × date × hour.
- [ ] `sensor_hourly`: per sensor × date × hour, median and spread.

## Verify

Unit tests on seeded fixtures for the trigger quirk, exclusions, sensor id churn and timezone
boundaries (DST, midnight). Then spot-check `presence_grid` for real days whose ground truth is
known (e.g. 2026-10-09: Athos out during working hours).
