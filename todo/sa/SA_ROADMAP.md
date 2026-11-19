# SA Roadmap: Learning Foundation

## Status: plan approved 2026-10-09. LF-0 to LF-3 deployed (2026-10-09/10). Layer 2 is a generic engine (`sa/layer2.py`) with a calendar family. **As of 2026-10-31 five cards read their learners**: `presence_deviation`, `household_unusual_day` (self-learning: learned features, and a bar calibrated to about one day in 14), `climate_deviation`, `attention_focus`, `wind_down_signal` (2026-11-01) and `rhythm_break_anomaly` (with a learned per-device minimum offline time). `departure_anomaly` stays in shadow (stay learner, 5-bit threshold, calendar suppression) and is the last rule on `entity_baselines`, whose device, household and room rows were retired (migration 0057). The shadow review (`scripts/sa_shadow_review.py`) judges episodes and flags per week, not agreement percentages. Stability is measured for the stay and daytime learners. Disk and lake monitoring is live. Layer 2 gained a second independent family (Deck network, 2026-11-01). Open: the `departure_anomaly` cutover and dropping `entity_baselines`, the card-feedback learner, transitions (SA-12, re-checked 2026-10-31, still stopped: no genuine cross-entity pairs), visitor-arrival cards. This doc is the entry point for all SA work.

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
| **LF-0c** ✅ | [todo_deck_learning_stream.md](todo_deck_learning_stream.md) | Capture what alfr3d_deck reports but does not keep: device context (battery, charging, DND, network, activity) and surface state history. Live 2026-10-10; learners wait for data | — |
| **LF-1a** ✅ | [todo_lf1a_sa_service_split.md](todo_lf1a_sa_service_split.md) | Lift the SA engine out of the daemon into `service_sa`, no behaviour change (deployed 2026-10-09; event-driven state deferred to LF-1c) | — |
| **LF-1b** ✅ | [todo_lf1b_bronze.md](todo_lf1b_bronze.md) | `sa-learner` + Parquet bronze export and backfill (deployed 2026-10-10; 23 MB for 3.8 M rows) | LF-1a |
| **LF-2** ✅ | [todo_lf2_silver_gold.md](todo_lf2_silver_gold.md) | Silver + gold, `sa_data_exclusions` (deployed 2026-10-10; presence = phones only, `observed` flag for collector outages) | LF-1b |
| **LF-2b** ✅ | [todo_lf2_silver_gold.md](todo_lf2_silver_gold.md) | Silver / gold for the LF-0b contexts: HA intervals, hourly scalar and state series, weather, email, daylight, `context_hourly` (deployed 2026-10-10). Found HA's home is still Novi Sad | LF-0b, LF-2 |
| **LF-4a** ✅ | [todo_lf4a_scalar_learner.md](todo_lf4a_scalar_learner.md) | Scalar-series learner over every numeric gold series; `climate_deviation` (2026-10-30) and `attention_focus` (2026-10-31) now read it | LF-3 |
| **LF-4b / LF-5a** 🟡 | [todo_lf4b_baseline_ports.md](todo_lf4b_baseline_ports.md) | Rate, device-rhythm and household-day learners. Cut over: `rhythm_break_anomaly`, `household_unusual_day`. `departure_anomaly` still in shadow | LF-3, LF-4a |
| **LF-3** ✅ | [todo_lf3_presence_learner.md](todo_lf3_presence_learner.md) | Inference contract + presence learner per user (deployed 2026-10-10; the 10-09 absence scores 3.35 bits, confidence 0.39, in walk-forward replay) | LF-2 |
| **LF-4** 🟡 | [todo_lf4_port_baselines.md](todo_lf4_port_baselines.md) | Four of five cutovers done; `entity_baselines` device, household and room rows retired (2026-10-31). Remaining: `departure_anomaly`, then drop `compute_entity_baselines` and the table | LF-3 |
| **LF-5** 🟡 | [todo_lf5_more_learners.md](todo_lf5_more_learners.md) | Rate learner done (LF-5a); drift done (2026-10-11); stability measured for stay and daytime (2026-10-31); remaining: card feedback learner, transition (SA-12, re-checked 2026-10-31, still stopped), visitor-arrival cards | LF-3 |
| **LF-6** 🟡 | [todo_lf6_layer2.md](todo_lf6_layer2.md) | Layer-2 engine built and live (generic fusion, calendar family, `away_unusual`, `day_off`, `household_unusual_day`, now self-learning); remaining: a second independent family beyond the calendar | LF-4, LF-5 |

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

## Next steps: plan of 2026-11-01

Written so a fresh session can resume from this doc alone. Gaps come from the 2026-11-01 review of
the roadmap, the LF docs and `littl31/src/assets/data/timeline.json`. Tick items here and in the
owning LF doc as they land.

### Step 1: finish LF-4 and refresh the public record (week of 2026-11-01)
- [x] Shadow review run 2026-11-01 (ssh `alfr3d@10.0.0.100`, repo at `~/alfr3d`; `ssh alfr3d@10.0.0.100 'cd ~/alfr3d && docker compose exec -T sa-awareness python - --days 7' < scripts/sa_shadow_review.py`). `departure_anomaly`, 6.7 of 7 days: legacy never fired; the learner raised 2 episodes (2.1/wk, under the 4/wk budget), both long stays at the edge of the 5-bit bar: user 1 (Athos) home continuously 76 h, p=0.028 / 0.019, conf 0.20-0.35; user 6 (Jenna) 26 h, p=0.024, conf 0.28 (below the 0.3 card floor). Verdict "NOT YET" only because 7.0 days are not complete. `inference_store.connect()` runs inside the container; `signal` is a reserved word, backtick it. Climate, attention and rhythm still say "NOT YET" because their window predates the 10-31 cutover and still counts legacy; rhythm's last learner episode was 10-30, so the post-cutover week is the real test.
- [ ] Watch the new `departure_anomaly` card and `sa_shadow_comparison` for a few days (the shadow comparison now compares the card with the learner it is built from). The review itself, run with `--days 14` on 2026-11-01, said WITHIN BUDGET. Old note: re-run the review on 2026-11-03 (>= 7 days). Before the cutover, adjudicate by hand whether Athos's 76 h stay (10-27 to 10-31, weekdays) was real or a phone that never left wifi; if it was real, the bar is working and the card would have shown once (conf 0.35).
- [x] Adjudicated 2026-11-01: Athos's 76 h flag (phone = device 4 `Littl3-Zen`, stay start 10-27 22:47 UTC to ~10-31 13:30 UTC) was **not** continuous presence. Athos confirms several walks under an hour; the stay rule's 45-minute bridge hides them. Visible in the data: arp gap 44 min on 10-28 22:04-22:48 UTC and 23 min on 10-30 22:13-22:35, each with 2 Deck cellular reports inside (4 of the 6 cellular reports in the window fall in such a gap). So the flag means "no absence over 45 min", not "never left". Consequences to settle before the cutover: (1) card wording must not say he has been home the whole time; (2) the LF-6 Phase 0 line "a single cellular report is noise (90 % inside arp-home)" is contaminated, because silver's arp-home includes bridged gaps, so short walks count as home; re-run that check against raw sightings; (3) the Deck could reset or annotate a stay (short outings) if (2) holds up. Thin data: n=2 walks.
- [x] **Per-person presence bridge: BUILT and DEPLOYED 2026-11-01 (PR #365).** `sa/presence_bridge.py` (pure rule: gaps that begin 00-06 local, 10-60 min, 95th percentile rounded up to 5, clamped 15-60; under 14 observed nights = 45 default; fewer than 5 naps = 15), silver `person_bridge` table + per-user `phone_islands`, `learners/bridge.py` stores it as `presence_bridge` profiles each night (first in `run_learners`), `stay.stay_state` + `ShadowRunner._stay_start` fold in newer sightings incrementally so a walk longer than the bridge starts a new live stay, `household_day.home_minutes` takes a per-user dict (daytime and household live paths). `build(gap_minutes=N)` still pins one number (replays). Replay on a copy of the production lake (NUC `sa-learner` `/tmp/replay`, scripts in the session scratchpad), flag-days of the stay learner 08-17..11-01 / stays >= 60 min in the last 28 days: Athos fixed20 4/45, fixed30 6/40, fixed45 8/31, **learned (25 min) 5/42**; Jenna 3 flag days at 45 and learned (both 45), 0 at 20 and 30; Vanja 0 everywhere (learned 45); Munja 0 flag days, learned 30 (median stay 411 min vs 725 at 45). Learned bridges: user 1 25 (20 naps/55 nights), 6 45, 8 30, 9 45, 10 30, 18 35; users with no night data keep 45. Athos's 10-28..10-31 stay is now 62.7 h (was split by the 44 min walk on 10-28; the 23 min walk on 10-30 is still bridged by 25). Not flagged under any variant: the legacy rule's one real firing (Athos, Saturday 09-12 evening), as the earlier replay found, because the stay model asks "unusually long", not "past his usual departure hour".
- [ ] (superseded by the item above, kept for the evidence) **Presence bridge (PRESENCE_GAP_MINUTES, 45 today; 30 before LF-2, raised because phones nap ~30 min).** Evidence gathered 2026-11-01 (NUC, 10-11..11-01): (a) Athos's phone, gaps vs Deck reports inside the gap: 15-30 min 7 of 9 had cellular (real outings), 30-45 min 7 of 8, 45-60 4 of 4; only 2 gaps of 15-45 min were wifi-only (a sleeping phone). His phone has 4.5 gaps of 20-45 min a week, 3 of 18 at night. (b) Other residents' phones nap far more, gaps of 20-45 min over 4 weeks (night 00-07 local): Jenna 212 (92 at night), Vanja 97 (28), Munja 68 (17), Elenka 40 (23), Predrag 20 (12). So **no single number fits**: 45 is right for Jenna and wrong for Athos, 30 splits Jenna's naps into false departures. Direction: learn the bridge per person from the phone's own night-time gap distribution (the phone is almost surely home 00-07), bounded to roughly 15-60 min, and validate it against Deck reports where a Deck exists. It changes silver `presence_intervals`, the stay and daytime profiles, `household_day.home_minutes` and the live stay start, so it needs a replay (flag-days/week for every resident under fixed 20/30/45 vs learned) before shipping; do it after the `departure_anomaly` decision, not inside it. Caveat: Deck cellular during a gap can also mean wifi off on a dozing phone; n is one phone.
- [ ] The NUC working tree is still behind `main` (it sits at da73bb97 with `services/service_sa` overlaid from the PR branch, which is main plus PR #365). After PR #365 merges, `git fetch && git restore --source=origin/main -- services/service_sa && git pull` (or stash first) to return it to a clean `main`. Merge PR #365 first.
- [x] Drop `entity_baselines`: migration 0062 written 2026-11-15 (drops the table, removes it from the storage-metrics procedure; downgrade rebuilds the full shape). Round-trip verified on a throwaway MySQL 8 (0061 to 0062 to 0061 to 0062). **DEPLOYED to the NUC 2026-11-15**: pre-migration dump `~/db_backups/alfr3d_backup_20261115_180705_pre_0062.sql.gz` (38.9 MB, verified trailer, contains the table), migrate image rebuilt, `docker compose --profile test run --rm migrate` 0061 to 0062, head confirmed 0062, table gone, storage-metrics procedure runs, sa-awareness/sa-learner/daemon healthy, no errors in 3 min of logs. The migration file is an untracked overlay in the NUC working tree (NUC is on detached `313f2413`, v0.5.0) until it lands on `main`; rollback = `alembic downgrade 0061` or restore the dump.
- [x] `departure_anomaly` cutover DONE and DEPLOYED 2026-11-01 (PR #365, commit ae7049ab): `check_departure_anomaly` now shows the stay learner's freshest deviation (confidence >= 0.3, one card per cycle, same mode and priority 2.7), worded "{name} hasn't been out in {N h | N days} — unusual for a {weekday}" with `stay_minutes`, `surprise_bits`, `confidence`, `p_stay_at_least`, `because`. Removed: the legacy `entity_baselines` query, `_departure_hours_by_bucket`, `compute_entity_baselines`, its 6-hourly schedule in `learner.py` and the DEPARTURE_* constants. 640 SA tests pass. Deployed by syncing `services/service_sa` from the PR branch to the NUC working tree (it was already identical to main, whose sa files are PR #364), `docker compose build/up -d --no-deps sa-awareness sa-learner` (v2), then one manual `silver.run_build()` + `learner.run_learners()` in `sa-learner`: 10 `presence_bridge` profiles (user 1 25 min, 6 45, 8 30, 9 45, 10 30, 18 35, the rest default 45), both containers healthy, no errors, departure rule quiet. NUC rollback: `~/rollback_bridge_deploy.{head,diff}` and `~/rollback_bridge_deploy.deck_network.py` (rebuild from `git restore --source=origin/main -- services/service_sa`). Not yet seen live: a departure card firing from the new path (unit-tested only). **The `entity_baselines` table itself is NOT dropped**; do that in a separate migration after a backup and a few days of the new card in production.
- [ ] (history) Decide the `departure_anomaly` cutover. Cut over only if learner-only time is explained, the 5-bit bar and calendar suppression hold, and the 2026-09-12 firing (Athos, Saturday evening) is not regressed; the stay-model replay did not flag it, so explain that first. Otherwise record why not.
- [x] `compute_entity_baselines` was already deleted (PR #365); the table drop is migration 0062 (see above).
- [ ] Sync `littl31` `timeline.json` (the `sa-learning-foundation` row is stale, dated 2026-10-12) and the Notion timeline row, in the same pass. Notion stays granular; the public JSON groups older rows (see memory note on timeline sync).

### Step 2: calibrate layer 2 against real data
- [~] Replay harness ([todo_lf7_replay_harness.md](todo_lf7_replay_harness.md), 2026-11-19, branch `feat/sa-replay-harness`, uncommitted): `python -m sa.replay` replays the three layer-2 rules and the stay learner under one report format, read-only; verified live on the NUC lake (28 days), tests pass locally. Calendar and Deck states are declared unreconstructable, not invented (the Deck family is not yet joined).
- [~] Set the calendar discount (70 %), the `day_off` 0.3x factor and the Deck-family discount/floor from observed flag rates (target about one flag-day in 14, like the household rule), not guesses. 2026-11-19: **no change justified**. One flag per rule in 28 days; the 0.3x factor is insensitive (sweep 0.3 to 1.0 all give 1 flag-day); the 70 % calendar discount cannot be measured without free/busy history; the Deck family is now reconstructed from bronze but none of the 11 presence deviations in 28 days coincided with a sustained Deck state, so its discount sweep is flat and it cannot be calibrated yet.
- [x] Replay-vs-live `stay` mismatch explained 2026-11-19 (todo_lf7_replay_harness.md): non-overlapping windows plus the learned presence bridge (2026-11-01) applied to history by silver; on the shared window (11-05 on) replay and live agree at 0 flags >= 0.3; the drift-cap guess was wrong. A parity check must compare only days with matching inputs.
- [x] `device_health` card, 2026-11-14: household hardware (devices owned by the `alfr3d` system user: camera, sensor) offline longer than max(2 h, 1.5 x the longest offline stretch the device itself ordinarily shows), so a nightly sleeper is not flagged by one. Those devices no longer get rhythm cards. Quiet while an integration is unreachable. Thresholds not tuned against a real outage (the clean period has none). Web icon added; **Deck has no dedicated rule yet** (falls back to the generic situational card): follow-up in `alfr3d_deck`.
- [x] Device rhythm `stability` is measured per day type (weekday vs weekend/holiday), 2026-11-14: availability flags use the stability of the day they fire on, so a weekday change (e.g. a school break) no longer holds down a weekend flag. Not yet verified on production data: whether a real school-day break (e.g. Vaxter iFone home at 11:00) now clears the 0.3 card floor; check after the next nightly fit.
- [ ] Wire `stability` for household day (add a daily feature to the drift detector); measure it for the daytime learner (fixed 0.5 today).
- [~] Replay-vs-live parity check (2026-11-19, `python -m sa.parity`, [todo_lf7_replay_harness.md](todo_lf7_replay_harness.md)): covers presence, stay, daytime, household day, scalar, event rate and device rhythm (approximate); not drift. Per-learner matching-inputs dates. 11-02 onward: presence MATCH (the one borderline day is a live `user.state` gap, 11-07 to 11-09), household MATCH, daytime 1 unexplained day, event rate quiet-day match, scalar 12 shared / 11 borderline / 4 live-only days (the live-only days are single reports crossing the bar where the hourly mean does not; the snapshot-versus-mean hypothesis was checked and refuted), device rhythm approximate (not evidence). Stay re-run pending post-deploy days. **Found while checking scalar: `attention:switch_count` crosses the 4-sigma bar in 6.4 % of walk-forward hours, steadily (3 to 14 a week); unlock_count 0 %, temperature 0.9 %, humidity 0.1 %. Fix built (branch `fix/sa-scalar-per-series-bar`, not deployed): a per-series calibrated bar; walk-forward `switch_count` flags fall from 53 to 4 hours over five weeks, the other three series are unchanged. Deploying changes which attention cards fire.**
- [x] **Live stay rows outlive the person's absence**: root cause found 2026-11-19 and fixed on branch `feat/sa-replay-harness` (not deployed): `device_history` logs the previous `last_online`, so right after an arrival `user.state` is online while the newest readable sighting is the last stay's, and `shadow._stay_start` scored that old stay as lasting until now (one spurious ~24 h row per arrival; no card, confidence under 0.3). `_stay_start` now returns None unless the newest sighting is within 31 min of now. Deploy needs approval; then advance `parity.MATCHING_INPUTS_SINCE`. Details in todo_lf7_replay_harness.md.

### Context learning 2/5 (2026-11-19): registry and capture ledger
- [~] [todo_lf8_context_registry.md](todo_lf8_context_registry.md), branch `feat/sa-context-registry`, **not merged or deployed**. Registry-generated `context_features` and `context_hourly` proven identical to the hand-written table on a copy of the production lake (5,265 rows, 0 differences, all 9 gold tables); stable identity in the live climate path (ESPHome ids 37885 then 37893 across the 2026-09-27 power cycle); ledger script matches the Phase 0 inventory; privacy scope enforced. Findings: no learner reads `context_hourly` yet; `calendar_busy_minutes` is zero-filled before the calendar was captured. Decisions pending: calendar NULL fix, automatic alias maintenance, ledger API route (needs migration 0063, plan and backup shown first).

### Step 3: close the live-scoring gaps (LF-1c)
- [ ] Event-driven `sa-awareness` (Kafka `event-stream`, in-memory state, reload on `sa-profiles-updated`).
- [ ] Hourly live scoring for scalar and rate profiles (nightly only today); an email live counter; `sa_data_exclusions` honoured in live counts.

### Step 4: widen the signal base (parallel, mostly capture)
- [x] Card-feedback capture, cross-repo: done. Backend + web 2026-10-31 (PR #360, migration 0058); the Deck already sends every field (checked 2026-11-14, `HttpAlfr3dClient.reportCardInteraction`). **Feedback semantics built 2026-11-14** (branch `feat/card-feedback-semantics`, migration 0061): checkmark `acked`, x `dismissed` (neutral), "Not useful" `not_useful` with an optional reason; see todo_card_feedback_loop.md. Verified live on a throwaway MySQL (migration, route, suppression); the Deck UI still needs an on-device check.
- [x] Implicit "acted on" linkage (Phase 2): checked 2026-11-14, stopped, not enough pairs; see the Phase 2 finding below.
- [ ] Card-feedback learner: Beta-Binomial per (rule, daypart) once a few hundred impressions with explicit interactions exist. Count on 2026-11-14: 46 impressions, 0 explicit interactions since capture began.
- [ ] Finish the Deck install-to-person mapping (a Deck with no location fix has no owner), then fit the DND and charging rhythm learners once a few weeks of Deck data exist.
- [ ] A third independent layer-2 family for people without a Deck (HA trackers, calendar free/busy history, or geofence after precise location). Then build "away trip".
- [ ] Transitions (SA-12): re-check monthly, with a concrete trigger of N organic cross-entity pairs. No calendar re-check is scheduled today.
- [ ] Calendar history: the table keeps 24 h, so "today's events" is only right for today; decide whether to keep a longer free/busy history.

- [x] `dedupe-now-playing-events` (2026-11-15, [todo](../todo_dedupe_now_playing_events.md)): every `play_start` was doubled (SA and the daemon monitor); the monitor now owns it, silver drops the historical duplicates. Learned `play_start` rates roughly halve at the next refit.

### Flag-budget check, 2026-11-15
The 11-14 "NOT YET" for `attention_focus` (18.7/wk) and `rhythm_break_anomaly` (13.6/wk) counted learner episodes over a window that straddled the cutover. Re-run on 2026-11-15 with `--days 14` (window now fully post-cutover): both **WITHIN BUDGET**, 3.5 published cards/wk each (7 in 14 days); learner episodes at conf >= 0.3 are 20/wk and 13.5/wk but only the published cards reach the household. The 12 attention "legacy only" lines are the 03:30 daily artefact. Nothing to fix; Step 2 calibration is no longer blocked on this.

### Phase 0 findings, 2026-11-14 (card feedback + gaps session; read-only, verified live on the NUC)

- **Repos.** `alfr3d` `main` = `bf6d42c7` (#384), `services/VERSION` 0.4.10, tag v0.4.10; the local checkout sits on the already-merged `fix/ha-device-identity` (0 commits ahead of `origin/main`, clean). `alfr3d_deck` `main` = `91a952a` (#62), tag v1.2.2. `littl31` `main` = `e6ae26f` with an uncommitted `timeline.json` edit (+13 lines, not mine).
- **NUC is NOT behind `main` any more** (the 11-01 note above is stale): working tree is clean `main` at `bf6d42c7`, identical to `origin/main`. The "return the NUC to clean main" item is done; nothing to propose.
- **Migrations.** Alembic head is 0060; next free is **0061**. Raw SQL sequence is separate: last file `migration_054_*.sql`, next **055**.
- **`card_interactions` in production** (rows since 2026-08-31): `shown` 110,346 with NULL surface (all before 10-31) + 550 deck + 61 web since 11-01; `tapped` 7 and `dismissed` 7, **all pre-0058 with NULL surface, none since**; `impression` 46 (deck 18, web 28), 46 distinct ids. Explicit interactions since the impression capture began: **zero**. The Beta-Binomial learner's "few hundred impressions with interactions" trigger is far off.
- **Double-counted `shown`: re-checked, partly resolved.** Impressions are one-per-display with an id, `surface` and `visible_ms` (web avg 20 s, deck avg 661 s, max 6,628 s). But `shown` still repeats every backend fetch by design: deck 550 rows over 28 distinct impressions (about 20 per display), web 61 over 46. So "one display = one impression" already holds; what is left is that `shown` is a per-fetch heartbeat feeding repetition damping (which has never fired, see the 10-11 finding).
- **Contract vs Deck.** The backend accepts `surface`, `impression_id`, `visible_ms`, `detail`, action `impression` (`routes/context.py`, `_card_interaction_extras`). The Deck already sends all of them (`HttpAlfr3dClient.reportCardInteraction`, `surface: "deck"` always; `CardInteractionTracker` mints ids and visible time). **The "Remaining: the Deck must send the same fields" item in Step 4 is stale and done** (Deck v1.2.x). Gap: `BriefRepository.dismiss` reports `dismissed` with no `impression_id`, so a Brief-card dismissal is not tied to its display. Only `dismissed` and `tapped` exist as explicit actions; no "got it" or "not useful" action and no reason handling yet (the enum is `shown, tapped, dismissed, expired, impression`).
- **Shadow review `--days 14` (run 11-14 23:39 UTC).** `departure_anomaly`: WITHIN BUDGET, 0 learner episodes at confidence >= 0.3 in 14 days (legacy never fired; 34.7 h of learner-only flags sit under the 0.3 card floor). `climate_deviation`: WITHIN BUDGET, 7 episodes (3.7/wk). `attention_focus`: NOT YET, 18.7 episodes/wk against a 4/wk budget (37 episodes; the 12 "legacy only" lines are a 03:30-daily artefact). `rhythm_break_anomaly`: NOT YET, 13.6/wk (27 episodes). Rhythm and attention are over the flag budget after their cutovers, which needs adjudicating before Phase 3 calibration.

### Phase 2 finding, 2026-11-14: implicit "acted on" linkage is NOT buildable yet (stopped at Phase 0, nothing built)

Checked on production over the last 8 weeks (card episodes = `shown` runs with gaps under 10 minutes). Per rule, the later event that would count as acting on the card, and what exists:

| rule | episodes | candidate "acted on" event | what the data shows |
|---|---|---|---|
| `empty_house_still_on` | 1 | a device turned off | one episode in 8 weeks: nothing to measure |
| `rhythm_break_anomaly` | 190 (26 subjects) | the device turned off | the subjects are LAN devices (phones, gateway, consoles); **0 of 26 match a controllable `smarthome_devices` row**, so there is no action a person could take on them. Not an acted-on candidate at all |
| `travel` (leave-by) | 10 | `left_area` within 90 min | **0 of 10** (only 17 `left_area` events exist in total) |
| `cross_surface_continuity` (music) | 33 | same-track `play_start` within 30 min | 2 of 33, and confounded: the card is built from that very playback |
| explicit taps | 7 in 56 days | `tapped` | all 7 predate the impression capture; none since |

Also: `device_command_history` only starts 2026-11-02 (120 user commands in 12 days), so an 8-week replay could not use it even where a pair existed. Fewer than a handful of usable pairs in every rule, so per the plan no linkage was invented and no replay was written.

**Re-check when** `empty_house_still_on` has about 10 episodes, or `device_command_history` holds 8 weeks (about 2026-12-28), or a rule is added whose subject is a controllable device. The most promising future linkage is the explicit one: `acked` on a card that suggests an action. (Proposed trigger; not agreed.)

### Phase 0 findings, 2026-11-18 (context-agnostic learning + layer 3 prompt; read-only, verified live on the NUC)

Gate: no assumption in the prompt blocks Phase 1; three need adapting (marked **ADAPT**). The lake coverage inventory is **not done** (only MySQL was inventoried), see the last bullet.

- **Repos.** `alfr3d` `main` = `22413d0b` (#421, README refresh), `services/VERSION` 0.5.0, tag v0.5.0 (the prompt's `a11cbcc` is two merges behind, harmless). `alfr3d_deck` `main` = `c1de56b` (#73), v1.2.4 released. **ADAPT: there is no `Littl31` sibling folder** under `/home/athos/Projects/Alfr3d`, so `timeline.json` cannot be edited from here until its location is given. NUC: clean `a11cbcc5` (v0.5.0), 15 services healthy, Alembic head 0062, next free 0063.
- **Captured today (production MySQL, first to last timestamp).**
  - Weather: `environment_history` holds observations (`kind='weather'`, 1,171 rows) **and forecasts** (`kind='forecast'`, 950 rows, plus `forecast_temp` / `forecast_rain_probability` / `forecast_conditions` on every row), 2026-10-09 to now. **ADAPT: forecast history is already stored**, so the "forecast history" item of the parallel capture track is mostly done; what is left is deciding whether this table is enough for lagged "forecast vs outcome" features.
  - Calendar: `calendar_events` holds 29 rows (events from 2026-10-09, but the table is purged after each event, so no free/busy history). Still a gap.
  - Indoor climate (ESPHome): `smarthome_sensor_history` 2.05 M rows, 13 devices, since 2026-09-16.
  - Deck: `deck_context_history` 3,929 rows, **2 installs**, since 2026-10-11 (network type is in it). `device_location_history` 2,387 rows, **4 installs / 2 users**, since 2026-09-11, coarse only.
  - Home Assistant: 53 `smarthome_devices` (HA sensors 32 of 38 online, 3 of 3 switches online, 4 of 4 media players online; ESPHome 8 rows online). **HA is reconnected**, no longer the all-offline outage.
  - `household_events` 68 k rows. `card_interactions` 111 k rows.
- **Outcome evidence for layer 3 (Phase 6 Phase 0).**
  - `device_command_history`: 153 rows, 2026-11-02 to 11-19, all with an origin (user 133, system 6, plus 14 ESPHome); every command succeeded. Nothing before 11-02.
  - `household_events` device verbs: `turned_on` 106 and `turned_off` 90 (to 11-19), `set` 59 (**last one 2026-10-09**, so brightness/`set` has stopped arriving), `routine:executed` 328. **HA is back and on/off rows now arrive**, so the "zero while offline" worry is resolved.
  - Card feedback: since the 11-15 Deck build, `acked` 4, `dismissed` 1 (deck), `not_useful` 1 (deck); impressions 35 web + 60 deck. So explicit interactions went from 0 to 6, still far from "a few hundred".
  - **Capture gap, not yet confirmed in code:** events come from `control_iot_device` commands; I did not find a producer for a state change with no API command (wall switch, HA automation). `ha_state_history` bronze (`ha_history.py`) does capture HA state changes with on-change timestamps for all entities, so the data may already be in the lake; whether any learner reads it for lights is open.
  - Card-to-action linkage: **not re-run this session**; the 11-14 finding stands (too few pairs), re-check due about 2026-12-28.
- **ESPHome orphan finding: partly stale.** Row IDs have changed before (aliases for retired ids 37885-37889 exist in `sa_sensor_aliases`, created 2026-10-10; the live rows are 37890-37897 created 09-27, and the aliased ids no longer exist). Silver already resolves a stable key (`host:name`) through the latest-snapshot identity view plus the alias table (`silver.py` around line 500-530), so **the lake-side learners are not keyed on row IDs**. I did not power-cycle the sensor (production, and not needed). **The live path still is:** `shadow.py` (climate scoring, around line 262-285) looks up `smarthome_devices` by name and queries `smarthome_sensor_history` by row ID, so a power-cycle that mints new ids would break live climate scoring until the lookup re-runs. Phase 2 should fix it at the registry boundary and move this lookup onto the stable key.
- **Shadow review `--days 14` (2026-11-19 00:xx UTC).** `attention_focus` WITHIN BUDGET (3.5 cards/wk); `climate_deviation` WITHIN BUDGET (0 cards); `departure_anomaly` WITHIN BUDGET (0 episodes at conf >= 0.3; 35 h learner-only below the card floor); `device_health` NOT YET (3.8 of 7 days); `rhythm_break_anomaly` NOT YET (4.5 published cards/wk, over the 4/wk budget, was 3.5 on 11-15). **ADAPT: the review script does not cover `away_unusual`, `day_off` or `household_unusual_day`**; those are layer-2 rules in `shadow.RULES`. Their 14-day layer-2 output from `sa_inferences`: `away_unusual` 4 rows over 3 days (mean conf 0.36), `day_off` 11 rows over 9 days (mean conf 0.07, below the 0.3 card floor), `household_day` 1 row (conf 0.33). That is volume only, not a verdict; Phase 1's replay is where a verdict belongs.
- **Family mapping.** `sa/layer2.py` lines 34-49: `FAMILY_BY_SIGNAL` (presence.home, device.online, device.session_minutes, presence.daytime -> network; calendar.busy -> calendar; deck.network -> deck) and `FAMILY_BY_KEY_PREFIX` (esphome: -> climate, ha:, attention:, email, event:). The climate family exists but no layer-2 rule consumes it yet (Phase 5's first weak witness).
- **Not done.** Per-signal hourly coverage over the last 30 days and lake retention (DuckDB over the Parquet lake in `sa-learner`), and who reads each signal. Do this as the first step of Phase 2's ledger, or on request before Phase 1.

### Step 5: later
- [ ] "Gathering likely tonight" (needs an occasional-visitor model: days since last visit, inter-visit gaps).
- [ ] Card policy for rate deviations (email burst, notification storm): a product decision for Athos.
