# Parallel capture track: proposals (2026-11-19)

Layer: capture and health | Roadmap: [SA_ROADMAP.md](SA_ROADMAP.md) | Prompt: "Parallel capture
track" (context-agnostic learning, 2026-11-18)

**Proposals only. Nothing here is built.** The prompt says: propose, then implement after each is
approved. Each item says what it needs, so a yes or a no is all that is required.

## 1. Forecast history

**Facts (production, 2026-11-19).** Forecasts are already stored. `environment_history` has 953
`kind='forecast'` rows and 1,175 `kind='weather'` rows since 2026-10-09 20:26, and both carry
`forecast_temp`, `forecast_rain_probability`, `forecast_conditions` and `forecast_updated_at` (a
forecast per fetch, roughly hourly). What is stored is **one window per fetch**: the OpenWeatherMap
5-day/3-hour entry nearest `now + 6 h` (`get_forecast(hours_ahead=6)`), recorded with the fetch time.
The window's own target time is not stored, so a forecast's lead is "about 6 h, give or take the
3-hour grid" and a forecast-versus-outcome pair has to be matched by that approximation. `kind` is an
`ENUM('weather','forecast')`. The lake already carries all of it (bronze `environment_history`); no
registry feature exposes the forecast columns yet.

**Options.**
- **A. Use what exists.** Register `forecast_temp_c`, `forecast_rain_probability` and a derived
  `forecast_error_6h` (observed at about `t + 6 h` minus the forecast issued at `t`) in the context
  registry (one `Feature` each, no capture change). Honest about the lead (about 6 h, plus or minus
  1.5 h). Costs nothing and unblocks the first "unusual for the forecast" covariates.
- **B. Store the target time.** Add a nullable `forecast_valid_at` column to `environment_history`
  and write the entry's `dt` (a one-line change in `update_db_forecast`). Makes lead exact. Needs a
  migration (next free revision 0063; 0062 is head), so a backup first.
- **C. Store several leads** (+3 h, +12 h, +24 h). Needs the ENUM widened (a migration) and more
  rows per fetch; only worth it if a learner shows it can use a forecast at all.

**Update 2026-11-19: option A approved and built** (`feat/sa-registry-forecast-and-calendar-null`): the forecast features are registered; 6-hour-lead forecast error is 1.55 C mean absolute so far. B is still open and waits for a held-out gain.

**Recommendation: A now; B if A shows a held-out gain.** It answers the question with no schema
change, and it is the cheaper way to find out whether forecasts are worth capturing better.
**Needs from you:** a yes to A. B and C need a migration, so I would show the plan and backup first.

## 2. Longer calendar free/busy history

**Correction first.** The prompt, the roadmap and my own earlier notes said the calendar table keeps
about 24 hours. **It does not.** `cleanup_calendar_events_event` has been 730 days since LF-0
(2026-10-09); 22 of the 29 events in MySQL ended over two days ago and are still there, and the lake
exports the table nightly (silver `calendar_busy` holds all 29). The replay now uses it (PR #428).

**What the history is, exactly.** `calendar_utils` deletes and re-inserts the events inside the sync
window (`now` to a future horizon, `calendar_utils.py:256`), so an event that is moved or cancelled
before it starts leaves no trace, while every event that has started is kept as it happened. That is
the right record for learning ("what the household actually had on"). It is not a record of what
was *planned* at some earlier moment.

**Options.** (1) Leave it: history keeps accumulating (29 events in six weeks, so it is thin but
real). (2) Keep planned-as-of-then snapshots: change the sync to append rather than replace; only
useful if "a booked event was cancelled" ever becomes a signal, which nothing needs today.

**Recommendation: leave it (option 1).** The "longer free/busy history" item in the prompt is
already satisfied. The retention is your choice only if you want it shorter than 730 days.
**Needs from you:** nothing; tell me if you want a different retention. Related, separate: the
registry's `calendar_busy_minutes` reads 0 ("free") for hours before 2026-10-09, when the truth is
"unknown" (`todo_lf8_context_registry.md`, decision 1).

## 3. Stale-fit alert

**Facts.** `run_learners()` wraps every fit in a `try/except` that only logs, so a learner that fails
nightly leaves its old profiles in place and nothing says so. Today all nine learners last fitted at
03:30 UTC on 2026-11-18 and every `fitted_to` is 2026-11-17, so nothing is stale now.

**A trap the alert must avoid.** `drift.apply_stability` rewrites `computed_at` on every profile whose
stability it caps (`UPDATE sa_profiles SET ... computed_at = %s`). A check on `MAX(computed_at)` per
learner would therefore read a *failed* fit as fresh for any learner the drift detector touches. The
reliable freshness signal is **`fitted_to`** (the last date of data the profile used), which only a
real fit advances; `presence_bridge` has no `fitted_to` (NULL) and needs its own rule.

**Constraint.** The card budget is fixed at 26 and the prompt says no new cards, so this cannot be a
card.

**Design.**
1. A pure function `stale_fits(stamps, now, max_age_days=2)` in `sa/` (testable, no DB), over
   `(learner, MAX(fitted_to))`, returning the learners behind by more than the allowance.
2. `sa-learner` writes one event per learner per night through the existing `event-stream` path
   (`subject_type: learner`, `verb: fit_ok | fit_failed`, with the exception text), so a failure is
   in `household_events` and the log, with no schema change.
3. `GET /api/health` (it exists) reports the stale learners, read-only, for the dashboard and any
   external monitor.
4. **Optional, your call:** also fold "learner fit stale" into the existing `check_system_health`
   urgent card ("SA says I'm blind"), which already exists for exactly this kind of problem and is
   not a new card. That changes the wording of a card people see, so it is not in the default plan.

**Update 2026-11-19: items 1 to 3 approved and built** (`feat/sa-stale-fit-alert`): `common/learner_health.py` (`stale_fits`, `summarize`, `fit_events`), `run_learners()` now records each learner's outcome and publishes `fit_failed` warnings plus one `fit_ok` or `fit_partial` summary per night to the event stream, and `GET /api/health` has an additive `learner_fits` block (`status` stays `ok`). Checked on real stamps: 9 learners ok; a simulated 3-day outage flags all 9. Item 4 (folding it into `check_system_health`) was not part of the approval and is not built.

**Recommendation: 1 to 3 now, 4 only if you want it surfaced in the app.** No migration, no new
card. **Needs from you:** a yes to 1 to 3, and a yes or no on 4.

## 4. Splitting `engine.py` (2,461 lines)

**Facts.** One class, `SAEngine` (line 277 onward), about 50 methods: the 26 `check_*` card rules
named in `DISPLAY_RULES`, the frame builder (`build_context_frame`), the suppression pass
(`_card_suppression_reason`, SA-1), health probes, and persistence helpers. Tests are tied to the
module namespace, which is what limits how it can be moved: `tests/test_sa_service.py` alone has 238
references to `sa.engine`, patching `engine.pymysql.connect` (42 places), `engine.get_producer` (12),
`engine.routing_utils.*`, `engine.inference_store.load_recent`, `engine.spotify_utils.*`. A
`pymysql.connect` patch survives a move (it patches the shared module object); an
`engine.get_producer` patch does not (it replaces a name in `engine`'s namespace), so code that calls
`get_producer` or similar must keep resolving through `engine`.

**Where the lines are** (approximate, by method position):

| area | lines | destination |
|---|---|---|
| frame, decide, suppression, shadow hook (277 to 650) | about 370 | `context_frame.py` (frame), `sa/suppression.py` |
| health: system, disk, emails (649 to 787) | about 140 | `sa/cards/health.py` |
| calendar, travel, focus, gatherings, party (787 to 1265, 2106 to 2192) | about 570 | `sa/cards/calendar.py` |
| learned and presence cards: rhythm, device health, departure, presence deviation, household day, attention, wind-down (1265 to 1673, 1892 to 2106) | about 620 | `sa/cards/learned.py` |
| media: now playing, cross-surface (1673 to 1892) | about 220 | `sa/cards/media.py` |
| environment: weather, advisory, climate, time, mood (2192 to 2437) | about 245 | `sa/cards/environment.py` |

**Plan (each step its own PR, existing tests unchanged, none of them edited).**
0. **Safety net first:** a golden test that runs `decide_displays` on a set of fixture frames and
   records every card's mode, priority and content now, so a refactor is checked against behaviour,
   not only against the unit tests. Also keep `MAX_DISPLAYS == len(DISPLAY_RULES) == 26`.
1. Pure helpers (`_span_text`, `_active_hours_mask`, the subject-key extractors, constants) to
   `sa/card_utils.py`; `engine` re-exports each name.
2. Suppression to `sa/suppression.py`, kept as a mixin on `SAEngine`.
3. Frame building into `context_frame.py`, `SAEngine.build_context_frame` a one-line delegate.
4. One mixin per area above (`HealthCards`, `CalendarCards`, `LearnedCards`, `MediaCards`,
   `EnvironmentCards`), `class SAEngine(HealthCards, CalendarCards, ...)`. Method resolution, the
   `DISPLAY_RULES` strings and `getattr` dispatch are unchanged. Methods whose tests patch an
   `engine.<name>` keep calling through `engine` (an `engine.get_producer()` call stays a call to
   that name, passed in or imported lazily).
5. `engine.py` ends as the orchestrator (`DISPLAY_RULES`, `check_situational_awareness`,
   `decide_displays`), a few hundred lines.

**Update 2026-11-19: step 0 built** (`test/sa-engine-split-safety-net`, `tests/test_sa_engine_structure.py`), with one change from the plan above. A golden test of card outputs would need a fixture frame and mocked databases for each of 26 rules, which is slow and still only checks what those fixtures happen to exercise. For a pure *move* a stronger and cheaper net exists: a snapshot of every `SAEngine` method's signature and a **hash of its source** (44 methods, plus the 3 module-level helpers), so after the split every moved method must still resolve on the class and be byte-identical, and an edit hidden inside a move is flagged by name. It also pins `DISPLAY_RULES`, `MAX_DISPLAYS == 26` and the names tests patch on the `engine` module (`engine.get_producer`, `engine.pymysql`, ...). Proven both ways: an added statement inside `check_time` fails it naming `check_time`; a verbatim move of a helper into another module (re-exported) passes. Steps 1 to 5 follow once this is on `main`, each its own PR. Regenerate the snapshot only on purpose: `UPDATE_ENGINE_SNAPSHOT=1 pytest tests/test_sa_engine_structure.py`.

**Acceptance per step:** the full SA suite green with no test file edited; the golden test unchanged;
the card budget assertion green; no behaviour change on a replay of the fixture frames.
**Risk and cost:** real but contained (steps 1 to 3 are small and mechanical; step 4 is the large
one). Roughly five to six PRs. **Needs from you:** a yes, and whether the golden test (step 0) should
come first as its own PR (my recommendation).

## Summary of what each needs

| item | recommendation | needs |
|---|---|---|
| 1. forecast history | A now (register the existing columns), B only if A shows gain | a yes to A; B needs a migration |
| 2. calendar history | already satisfied; leave | nothing |
| 3. stale-fit alert | 1 to 3 now (function, per-night events, `/api/health`); 4 optional | a yes, and yes or no on 4 |
| 4. engine.py split | six small PRs behind a golden test | a yes |
