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
- [ ] Drop `entity_baselines` (backup first, own migration) after a few days of the new card.
- [x] `departure_anomaly` cutover DONE and DEPLOYED 2026-11-01 (PR #365, commit ae7049ab): `check_departure_anomaly` now shows the stay learner's freshest deviation (confidence >= 0.3, one card per cycle, same mode and priority 2.7), worded "{name} hasn't been out in {N h | N days} — unusual for a {weekday}" with `stay_minutes`, `surprise_bits`, `confidence`, `p_stay_at_least`, `because`. Removed: the legacy `entity_baselines` query, `_departure_hours_by_bucket`, `compute_entity_baselines`, its 6-hourly schedule in `learner.py` and the DEPARTURE_* constants. 640 SA tests pass. Deployed by syncing `services/service_sa` from the PR branch to the NUC working tree (it was already identical to main, whose sa files are PR #364), `docker compose build/up -d --no-deps sa-awareness sa-learner` (v2), then one manual `silver.run_build()` + `learner.run_learners()` in `sa-learner`: 10 `presence_bridge` profiles (user 1 25 min, 6 45, 8 30, 9 45, 10 30, 18 35, the rest default 45), both containers healthy, no errors, departure rule quiet. NUC rollback: `~/rollback_bridge_deploy.{head,diff}` and `~/rollback_bridge_deploy.deck_network.py` (rebuild from `git restore --source=origin/main -- services/service_sa`). Not yet seen live: a departure card firing from the new path (unit-tested only). **The `entity_baselines` table itself is NOT dropped**; do that in a separate migration after a backup and a few days of the new card in production.
- [ ] (history) Decide the `departure_anomaly` cutover. Cut over only if learner-only time is explained, the 5-bit bar and calendar suppression hold, and the 2026-09-12 firing (Athos, Saturday evening) is not regressed; the stay-model replay did not flag it, so explain that first. Otherwise record why not.
- [ ] After the cutover: backup, then delete `compute_entity_baselines` and drop `entity_baselines` in one migration.
- [ ] Sync `littl31` `timeline.json` (the `sa-learning-foundation` row is stale, dated 2026-10-12) and the Notion timeline row, in the same pass. Notion stays granular; the public JSON groups older rows (see memory note on timeline sync).

### Step 2: calibrate layer 2 against real data
- [ ] Replay harness: walk-forward over the lake for every layer-2 rule, with calendar and Deck states reconstructed.
- [ ] Set the calendar discount (70 %), the `day_off` 0.3x factor and the Deck-family discount/floor from observed flag rates (target about one flag-day in 14, like the household rule), not guesses.
- [ ] Wire `stability` for device rhythm and household day (add a daily feature to the drift detector); measure it for the daytime learner (fixed 0.5 today).
- [ ] Replay-vs-live parity check for every live-scored learner (this caught the household device-count bug on 2026-10-12).

### Step 3: close the live-scoring gaps (LF-1c)
- [ ] Event-driven `sa-awareness` (Kafka `event-stream`, in-memory state, reload on `sa-profiles-updated`).
- [ ] Hourly live scoring for scalar and rate profiles (nightly only today); an email live counter; `sa_data_exclusions` honoured in live counts.

### Step 4: widen the signal base (parallel, mostly capture)
- [ ] Card-feedback capture, cross-repo. Backend + web are done (PR #360, 2026-10-31, migration 0058: `surface`, `impression_id`, `visible_ms`, `detail`, `impression` action). **Remaining: the Deck must send the same fields** (`CardInteractionTracker` in `alfr3d_deck`). Once a few hundred impressions with interactions exist, build the Beta-Binomial per (rule, daypart) learner (see todo_lf5_more_learners.md).
- [ ] Finish the Deck install-to-person mapping (a Deck with no location fix has no owner), then fit the DND and charging rhythm learners once a few weeks of Deck data exist.
- [ ] A third independent layer-2 family for people without a Deck (HA trackers, calendar free/busy history, or geofence after precise location). Then build "away trip".
- [ ] Transitions (SA-12): re-check monthly, with a concrete trigger of N organic cross-entity pairs. No calendar re-check is scheduled today.
- [ ] Calendar history: the table keeps 24 h, so "today's events" is only right for today; decide whether to keep a longer free/busy history.

### Step 5: later
- [ ] "Gathering likely tonight" (needs an occasional-visitor model: days since last visit, inter-visit gaps).
- [ ] Card policy for rate deviations (email burst, notification storm): a product decision for Athos.
