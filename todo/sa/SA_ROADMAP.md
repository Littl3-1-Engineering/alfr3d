# SA Roadmap: Learning Foundation

## Status: plan approved 2026-10-09. LF-0, LF-0b, LF-1a, LF-1b, LF-2 and LF-3 deployed (2026-10-09/10); LF-2b (silver / gold for the new contexts) and the learner families next. This doc is the entry point for all SA work.

Every SA doc lives in `todo/sa/` and carries a `Layer:` / `Roadmap:` line under its title that
points back here. Work proceeds by LF phase (below); each phase has its own `todo_lfN_*.md`.

## Why

Prompted 2026-10-09 (a Friday): Athos is normally home 9-17 on weekdays, was out all day, and
nothing in the SA engine could notice. Every existing anomaly rule hand-builds its own baseline
(lookbacks 30/120/14 days, sample floors 5/8/14/10/200, statistics min/max vs. mode hour vs.
median±2σ vs. fixed thresholds), all squeezed into one `entity_baselines` table whose columns mean
different things per entity type. Nothing models *where people normally are*, nothing carries a
confidence, and `compute_entity_baselines()` runs inside the daemon loop (~175 s on the NUC) and
blocks every SA card while it does.

**Goal:** a learning foundation over ~2 years of logged data.
1. **Data layers** (bronze → silver → gold) that keep every variable, clean it once, and shape it
   for learning.
2. **Layer-1 (L1) inferences:** learned profiles, deviations, predictions, transitions and drift,
   each with a probability and a **confidence**, written to one shared inference contract.
3. **Layer-2 (L2) inferences:** combinations of L1 inferences weighted by confidence. Only the
   interface is fixed now.

Anomaly detection is one learner among several. `check_*` rules become *consumers* of inferences
instead of each computing its own baseline.

## Service boundaries

The split is by **speed**, not by domain. SA is awareness built on learned data, so one service
owns both.

- **`service_daemon`**: a fast loop engine and nothing else. Schedules, routines, arp scan,
  IoT/calendar/ESPHome sync, mute. No SA rules, no context frame, no baselines, no long queries.
- **`service_sa`**: one codebase, one image, two compose entries.
  - **`sa-awareness`** (fast path): event-driven from Kafka `event-stream`, with household state
    and `sa_profiles` held in memory (reloaded on Kafka `sa-profiles-updated`). Each event or a
    ≤60 s tick builds the context frame, scores L1 inferences (cheap arithmetic), runs the rules,
    applies card suppression, and publishes to the existing `situational-awareness` topic
    (`service_api` `consume_sa` unchanged) and to a new `sa-inferences` topic. MySQL reads are
    small indexed ones only.
  - **`sa-learner`** (slow path): DuckDB + pyarrow over the Parquet lake. Nightly bronze/silver/
    gold, `fit` every 6 h → `sa_profiles` → `sa-profiles-updated`, drift detection.
  - `Learner` classes are shared: `fit` runs in the learner, `score` in awareness, always the same
    version.

## Storage

1. **MySQL = operational store, 730-day retention on every SA variable**, enforced by MySQL
   EVENTs (the migration 039 pattern, so retention runs whether or not any service is up).
2. **Parquet lake (`sa_lake` volume) = learning store**, mounted only on `sa-learner`.
   zstd, Hive-partitioned `layer/table/date=YYYY-MM-DD`.
   - **bronze**: append-only copy of every source, exported nightly by watermark, plus daily
     snapshots of current-state tables. Silver and gold can always be rebuilt from it.
   - **silver**: cleaned and conformed (below).
   - **gold**: feature grids for learners.
3. **Inferences and profiles go back to MySQL** (`sa_inferences`, `sa_profiles`): small, and
   readable by the API and Deck through existing paths.

Why not bronze/silver/gold in MySQL: scanning 30M+ `device_history` rows is exactly the 175 s
cost today. DuckDB over columnar Parquet does it in seconds, outside the OLTP database.

### Retention: what the 2026-09-13 change actually covered

The Notion row "SA data retention extended to 2 years across event-log tables" (commits
`29fa3e21`, `fb97695e`, migration 039) covered **four tables only**: `household_events`,
`attention_telemetry_history`, `card_interactions`, `device_location_history`
(`smarthome_sensor_history` was later created at 730 days). Not covered, **fixed by LF-0 on 2026-10-09**:

| Variable | Today |
|---|---|
| `device_history` (device presence) | 180 days, deliberately left out as "the ~7 GB decision"; never revisited |
| Weather (`environment` row) | no history, overwritten every 1-4 h |
| `calendar_events` | deleted 24 h after each event ends |
| `listening_history` | unbounded |
| `device_command_history` | dead table, no writer (LF-0 rebuilt it as a full command log: params, outcome, origin) |

## Signals: not only people and devices

SA covers every context ALFR3D senses: IoT states, weather, date and time of year, indoor climate,
calendar, email, notifications, geofencing, what the Deck reports. All of it reduces to four signal
shapes (state, scalar, event stream, transition), each with a learner family; the presence learner is
the first "state" learner, and the confidence function, tables and walk-forward evaluation are
shared. The binding constraint is **what is captured**, not modelling: several contexts have little
or no history, and Home Assistant discards its own after ~10 days. Full inventory, gaps ranked by
loss rate, and the proposed order: [todo_signal_inventory.md](todo_signal_inventory.md).

## Inference contract (`sa_inferences`)

`id`, `layer` (1|2), `kind` (profile|deviation|prediction|transition|drift), `subject_type`,
`subject_id`, `signal` (e.g. `presence.home`), `context` JSON (e.g. `{"dow":5,"hour":10}`),
`window_start`, `window_end`, `observed` / `expected` JSON, `probability` (0-1), `surprise`
(−log₂ p), **`confidence`** (0-1), `n_eff`, `evidence` JSON (source refs, or parent inference ids
for L2), `learner`, `learner_version`, `computed_at`, `expires_at`.

Learned distributions go in `sa_profiles`, keyed by learner, subject, signal and context. This
replaces `entity_baselines`' per-type column reuse.

### Confidence, defined once

`confidence = sufficiency × coverage × source_quality × stability`

- **sufficiency**: effective sample size / posterior width.
- **coverage**: share of expected observations actually present in the window (sensor dropouts,
  arp outages lower it).
- **source_quality**: per-source reliability learned in silver (per-device arp artifact rate;
  2 km coarse location scores low).
- **stability**: lowered by recent drift or a regime change (e.g. the house move).

## L1 learner toolbox

All learners implement `fit(gold) → profiles` and `score(now, state) → inferences`.

| Learner | Technique | Replaces / enables |
|---|---|---|
| **Presence profile** (first proof, LF-3) | P(home) per **user** (residents *and* visitors) × day-of-week × hour; time-decayed Beta-Binomial (8-week half-life) with partial pooling dow → weekday/weekend → all | SA-3's departure baseline; deviation "usually home Fri 9-17, away now"; next-24 h prediction = visitor anticipation |
| Time-of-event | circular mean/spread for departure, arrival, first/last activity | SA-3/SA-10 mode hour; fixes the midnight-wraparound bug |
| Scalar sensor | robust median/MAD per hour-of-day (season-aware after a year) → robust z, tail probability | SA-9 climate, SA-2 attention |
| Rate / count | Poisson / negative-binomial expected rate per dow × hour | device activity, event rates, inputs to `household_unusual_day` |
| Session duration | empirical quantiles of on-duration from silver `device_sessions` | rhythm-break `still_on_past_typical` |
| Transition | P(B within 10 min of A), Beta confidence, sample floor | SA-12 |
| Drift | Page-Hinkley / CUSUM on gold daily features | regime shifts (house move); feeds `stability` |

First L2 candidate: `household_unusual_day`, rebuilt as a confidence-weighted combination
(Fisher's method) of L1 tail probabilities.

## Silver: data-quality fixes done once, not per rule

- **`presence_intervals`**: per user, from **phone** sightings only (device_type resident/guest;
  hardware stays home when its owner leaves). Built from distinct `last_online` values, never
  from `state` (the trigger logs `OLD.state`). Came/went events and geofence are left out as
  sources for now (see todo_lf2_silver_gold.md); the `source` column keeps room for them.
- **`device_sessions`**: derived from gaps, with the trailing-offline-gap quirk fixed.
- **`sa_data_exclusions`** (MySQL, hand-editable): time windows/sources to drop. Seeds: test
  bursts 2026-09-16 03:02-03:04, 09-16/17, 10-01/02; device 60's self-pair volume `set` spam;
  verification sessions.
- **`day_context`**: dow, weekday/weekend, holiday, calendar-busy, daylight, season.
- Every timestamp as both `ts_utc` and `ts_local`, from one timezone source.

## Phases

| Phase | Doc | What | Depends on |
|---|---|---|---|
| **LF-0** ✅ | [todo_lf0_retention_gaps.md](todo_lf0_retention_gaps.md) | 730-day retention and history capture for every SA variable in MySQL (deployed 2026-10-09) | — |
| **LF-0b** ✅ | [todo_signal_inventory.md](todo_signal_inventory.md) | Capture the missing contexts (deployed 2026-10-10): Home Assistant entity history (79 entities, 11 days), 12 months of Gmail metadata (3,656), ESPHome binary sensors / lights | — |
| **LF-0c** | [todo_deck_learning_stream.md](todo_deck_learning_stream.md) | Capture what alfr3d_deck reports but does not keep: device context (battery, charging, DND, network, activity) and surface state history | — |
| **LF-1a** ✅ | [todo_lf1a_sa_service_split.md](todo_lf1a_sa_service_split.md) | Lift the SA engine out of the daemon into `service_sa`, no behaviour change (deployed 2026-10-09; event-driven state deferred to LF-1c) | — |
| **LF-1b** ✅ | [todo_lf1b_bronze.md](todo_lf1b_bronze.md) | `sa-learner` + Parquet bronze export and backfill (deployed 2026-10-10; 23 MB for 3.8 M rows) | LF-1a |
| **LF-2** ✅ | [todo_lf2_silver_gold.md](todo_lf2_silver_gold.md) | Silver + gold, `sa_data_exclusions` (deployed 2026-10-10; presence = phones only, `observed` flag for collector outages) | LF-1b |
| **LF-3** ✅ | [todo_lf3_presence_learner.md](todo_lf3_presence_learner.md) | Inference contract + presence learner per user (deployed 2026-10-10; the 10-09 absence scores 3.35 bits, confidence 0.39, in walk-forward replay) | LF-2 |
| **LF-4** | [todo_lf4_port_baselines.md](todo_lf4_port_baselines.md) | Port SA-9/SA-2/rhythm/SA-3/SA-10 to learners, shadow then cut over, retire `entity_baselines` | LF-3 |
| **LF-5** | [todo_lf5_more_learners.md](todo_lf5_more_learners.md) | Rate, transition (SA-12), drift, visitor-arrival prediction | LF-3 |
| **LF-6** | [todo_lf6_layer2.md](todo_lf6_layer2.md) | Layer-2 design | LF-4, LF-5 |

LF-0 and LF-1a are independent and can run in parallel.

Cross-cutting, not an LF phase: [todo_disk_and_lake_monitoring.md](todo_disk_and_lake_monitoring.md)
(alert before disk, lake or MySQL growth runs out of room; the lake is deliberately uncapped).

## Existing SA items by layer

| Item | Doc | Layer | Status (2026-10-09) | LF impact |
|---|---|---|---|---|
| SA-11 event log | todo_household_event_log.md | data | deployed | LF-1b bronze source |
| Retention | todo_sa_data_retention_3yr.md | data | 4 tables at 730 d | LF-0 closes the rest |
| SA-4 context frame | todo_context_frame.md | awareness runtime | deployed | LF-1a moves it to `sa-awareness` |
| SA-8 BLE presence | todo_ble_presence_sensing.md | input | dead at Phase 0 | silver source if revived |
| SA-9 ESPHome climate | todo_esphome_situational_awareness.md | input + L1 consumer | deployed, `climate_deviation` never fired live | LF-4 scalar learner |
| Device location / geofence | todo_device_location_reporting.md | input | deployed, coarse only, n=1 | LF-2 presence source |
| Precise location | todo_precise_location.md | input | not started | raises location source_quality |
| CEP | todo_context_exchange_protocol.md | input | phases 1-3 done | LF-2 absorbs presence merge |
| SA-2 attention | todo_attention_telemetry(_history).md | input + L1 consumer | deployed | LF-4 scalar learner |
| Rhythm break | todo_rhythm_break_anomaly.md | L1 consumer | deployed | LF-4 session learner |
| SA-3 departure anomaly | todo_departure_anomaly.md | L1 consumer | fired once (09-12) | LF-3/LF-4 presence learner |
| SA-10 generalized baselines | todo_generalize_entity_baselines.md | L1 learner (legacy) | deployed, never fired live | LF-4 port; `household_unusual_day` → L2 |
| SA-12 transitions | todo_transition_learning.md | L1 learner | stopped, re-check ~11-01 | LF-5 on silver |
| SA-1 card feedback | todo_card_feedback_loop.md | consumer feedback | deployed on all surfaces | LF-1a moves suppression; learning signal in LF-5 |
| SA-7 conferencing | todo_calendar_conferencing.md | input + consumer | waiting on real invite | LF-0 calendar history |
| SA-6 routing / leave-by | todo_self_hosted_routing.md | consumer | live | LF-1a move |
| Household composition | todo_household_composition.md | L1 consumer (fixed) | deployed | LF-1a; visitors in LF-3/LF-5 |
| Cross-surface continuity | todo_cross_surface_continuity.md | consumer | deployed | LF-1a move |
| Leave-by demo | todo_leave_by_demo.md | consumer (demo) | done | none |

## Principles carried forward

- Phase 0 against real production data before trusting any constant. Several past constants were
  invented and wrong (300 m geofence, raw min/max climate band).
- Cards stay ambient observations, never welfare checks (SA-3's tone constraint).
- Doc claims are checked against the live DB before acting on them. "Never fired" was stale twice.
