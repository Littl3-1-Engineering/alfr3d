# LF-10: discovery screen and derived targets (Context learning 4/5), PLAN

Status: **plan approved 2026-11-19.** Build order, each its own PR: (1) **target registry and
validation: built 2026-11-19** (`sa/targets.py`, `tests/test_sa_targets.py`); (2) nightly screen
`sa/screen.py` and its tests: **built 2026-11-19** (see the step 2 notes below); (3) migration 0064, the findings API and the
`learner.py` stage: **built, merged (#449) and DEPLOYED 2026-11-19; migration 0064 RUN on production** (see below). Decisions
below.

**Step 1 verified live, read-only on the NUC lake (2026-11-19):** `validate()` and
`validate_queries()` clean; the three queries return 3,245 hourly values each and reproduce the
sizing numbers (guests_home non-zero 1,650, max 2; house_empty 182; away_minutes non-zero 2,791,
max 240); `check_kind` passes for all three. Not live: nothing is deployed and nothing reads the
registry yet. Note the forecast candidates read the long-form `context_features`, not
`context_hourly` (the forecast features are not columns of it). Prompt: Notion "Claude Code prompt:
context-agnostic learning and layer 3", Phase 4. Builds on LF-8 (registry: which signals exist) and
LF-9 (`sa/covariates.py`: `screen` for continuous targets, `screen_rates` for binary and count).

## What it is

1. A **derived-target registry**: outcomes the household produces (guests home, time away, empty
   house) declared as definitions over silver/gold, not coded into a learner.
2. A **nightly screen**: for every declared target, every candidate feature and lag, record
   held-out gain and effect size, or an explicit insufficient-evidence row, in a new table
   `sa_covariate_findings`. **No cards, no actuation**, and the 26-card budget is untouched.
3. A **read-only owner API** over the findings, shaped like the Teach-me contract (profile,
   confidence, evidence). The UI waits for the owner's review.

## 1. Target registry (`sa/targets.py`)

Same shape as the context registry (`Target` dataclass, `REGISTRY`, `validate()`), because a new
outcome should be one registration plus a validation run:

`Target(key, kind, query, cell, candidates, min_events, privacy, description)`

- `kind`: `continuous` (screened by `covariates.screen` on the residual after the hour-of-week mean),
  `count` or `binary` (screened by `covariates.screen_rates`). Chosen by the registrant, checked by
  `validate()` against the data (a "continuous" target that is 90 % zero is rejected).
- `query`: SQL over the registered silver/gold views returning `(bucket_utc, value)`, one row per
  observed hour. `validate()` runs it on a tiny synthetic lake and rejects a query that returns the
  wrong columns, duplicate hours, or a value at hour t that changes when only later hours change
  (a leakage check: the value must depend on hour t alone).
- `cell`: the structure the learner already models, default hour of week. `min_events`: default 20.
- `candidates`: explicit `(feature key, lags)`, at most 8 per target (the engine's budget). Features
  come only from `context_registry.learner_candidates()`: household-scoped always, owner-opened only
  if opened, **restricted never** (so precise location can never be screened).
- `privacy`: a target is household-scoped; per-person targets are not proposed here.

### Proof targets (three, none hard-coded in a learner)

Numbers from the real lake, 2026-11-19 (3,245 observed hours since 2026-04-12):

| target | kind | definition | real data |
|---|---|---|---|
| `guests_home` | count | persons with `user_type = 'guest'` home at least 30 min of the hour | non-zero in 1,650 hours, max 2 |
| `house_empty` | binary | no resident or owner home the whole observed hour | 182 hours |
| `away_minutes` | continuous | resident-and-owner minutes NOT home in the hour, summed over people | mean 86.5; 0 in 454 hours |

Honest labels: `away_minutes` is the owner's "time outdoors" idea in the only form the data
supports. It means *away from the house*, not outdoors, and is named that way. "Guest" is the
household's own device tag, and it includes regular visitors (Elenka 1,265 home-hours, Predrag 701,
Vesna 245), so `guests_home` is "tagged-guest people home", not strangers.

Overlap limits what can be found: outdoor weather has about 860 hours of overlap with these hours,
calendar busy minutes only since 2026-10-09, forecasts only since the #430 rebuild lands. Most
candidates will therefore report insufficient evidence for a while; that is the correct output.

## 2. Nightly screen (`sa/screen.py`, stage in `learner.py`)

`run_screen(lake_dir, conn)` runs after `run_learners()` as a best-effort stage, the way
`run_ledger()` does: it logs and carries on, never stops the nightly job.

- For each target: load `(t, value)`, build pairs per candidate and lag (`covariates.lagged_pairs`
  or `rate_pairs`), call the right screen with a **fixed budget** (8 candidates per target, 99
  permutations, fixed seed), and store every candidate: `effect`, `insufficient_evidence` (with the
  reason) or `not_tested`. Findings below the floor are stored as insufficient evidence, **never as
  a result**.
- A target with no data still writes one row (`reason: no data`), so a night's run provably covers
  every declared target.
- Cost: slope screen about 99 x 5 ms per candidate that clears the gain bar, rate screen linear in
  rows; three targets finish in seconds. No retries, no re-seeding: a night cannot manufacture
  significance.
- Retention: findings are kept 90 days of nightly runs (a finding that holds for weeks is worth more
  than one that appears once), pruned by the same stage. Proposal below.

## 3. Table `sa_covariate_findings` (migration 0064, NOT run)

`run_date DATE, target_key, feature_key, lag_hours INT, method ('slope'|'rates'), status
('effect'|'insufficient_evidence'|'not_tested'), reason VARCHAR, n INT, effect DOUBLE, effect_unit
VARCHAR, improvement DOUBLE, p DOUBLE, p_adjusted DOUBLE, fitted_from DATE, fitted_to DATE,
evidence JSON, computed_at DATETIME`. Primary key `(run_date, target_key, feature_key, lag_hours)`,
index on `(target_key, status)`. Raw SQL `migration_057_sa_covariate_findings.sql` plus the Alembic
wrapper `0064_sa_covariate_findings.py` (next free revision after 0063, to be checked again at
write time); downgrade drops the table. Additive: no existing table changes.

**Production plan (when you say go):** a fresh verified `mysqldump` backup first, as for 0063;
merge; fast-forward the NUC; `docker compose --profile test run --rm migrate`; restart `sa-learner`
and `service-api`; verify `alembic current` = 0064; run the stage once, then check the rows.
Rollback: `alembic downgrade 0063` (drops the one table; the stage then logs and carries on) or
restore the dump. Before the migration is applied the API answers `available: false`, so code can
merge and deploy ahead of it (as the ledger route did).

## 4. API: `GET /api/context/findings` (read-only)

Latest run per target, `?target=` and `?status=` filters. Each finding carries the Teach-me shape:
`profile` (target, feature, lag, method), `confidence` (status plus `p_adjusted`, `improvement`,
`n`), `evidence` (effect with unit, held-out window, reason). `effect` rows first, then the closest
`insufficient_evidence` rows by `p_adjusted`, so "nothing yet, closest is X" is visible. Same
access as `/api/context/ledger`.

## 5. Acceptance (from the prompt) and tests

- A night's run writes findings or explicit insufficient-evidence rows for **every** declared
  target.
- A planted synthetic relationship in a test is found; a planted null is not.
- Budget and floors are enforced by tests (a target offering 12 candidates screens 8 and lists 4 as
  `not_tested`; an under-floor candidate is never `effect`).
- `validate()` rejects a leaking query, a wrong-kind target and a restricted feature.
- `MAX_DISPLAYS == len(DISPLAY_RULES) == 26` unchanged; no card, no device command.
- CI green; docs updated; Notion row "Context learning 4/5" updated (wording shown to you first).

## Decisions (owner, 2026-11-19: yes to all)

1. **Proof targets:** `guests_home`, `house_empty`, `away_minutes`, named as above. Approved.
2. **Retention:** 90 days of nightly findings. Approved.
3. **Lags:** default set `{0, 1, 3, 6, 24}` hours per feature, trimmed to the 8-candidate budget per
   target, declared on each target. Approved.
4. **API access:** ungated read, like `/api/context/ledger` (the first of the two options offered).
   Recorded as the reading of "yes to all"; say so if a resident-role gate is wanted instead.
5. **Table design** for `sa_covariate_findings` (migration 0064): approved. Writing it does not
   authorise running it: the verified backup and the plan are shown first, then the owner says go.

## Step 2 built (2026-11-19): `sa/screen.py`, and what building it found

`run_screen(lake_dir)` returns one row per declared candidate-lag per target (or one row saying why
there are none: no presence tables, `context_hourly` missing, no observed hours, the target's kind
not fitting its data). It refuses to run if `targets.validate` / `validate_queries` find a problem,
so a registry that could fish never runs. Reasons are specific ("the feature has no data in the lake
yet", "only 2 events (need 20)", "did not reduce held-out error enough", "not distinguishable from
chance after multiple-testing correction"). Rows are plain dicts shaped for the table in step 3.
Tests (`tests/test_sa_screen.py`, 13 s): a planted effect is found; an independent series and a
planted null are not; every declared target and candidate is covered even with tables missing;
a shared trend is not an effect; reproducible; refuses an unsound registry.

**Verified live, read-only on the NUC (a throwaway lake copy rebuilt with the deployed image, then
deleted; the production lake has no `context_features` until tonight's 03:30 UTC build):** 3 targets,
23 candidate rows in 0.7 s, 0 effects: `guests_home` (2 events in the overlap) and `house_empty`
(18) are under the event floor, `away_minutes` and the calendar/holiday/daylight/forecast
candidates show no gain. The screen cannot yet be stored (no table) and is not wired into the
nightly job.

**What building it found (see also the correction in todo_lf9):** the engine's permutation
resolution made effects impossible, and the whole-history weather anomaly let a shared seasonal
trend pass for a cause. Both fixed, both tested, and the earlier probe results re-stated.

**For step 3 / the API:** per-target Holm does not control error across targets or nights (about
`0.05 x targets` false effects a night). Proposed: store every night, and have the API show how many
of the last N nights a candidate was an `effect`, so a one-night flicker is visible as one.

## Step 3 built (2026-11-19): table, store, stage, API. Migration 0064 NOT run on production.

- `setup/migration_057_sa_covariate_findings.sql` + `setup/migrations/versions/0064_sa_covariate_findings.py`
  (next free revision after 0063, checked): one table, `sa_covariate_findings`, primary key
  `(run_date, target_key, feature_key, lag_hours)`. Downgrade drops it.
- `screen.store(conn, rows)`: one transaction; a re-run of the same night replaces that night's
  rows; runs older than 90 days are pruned; rolls back on error. `screen.run(lake, conn)` screens and
  stores. `learner.run_discovery_screen()` is a best-effort stage after the learners (a missing
  table, an unsound registry or any error is logged and the nightly job carries on).
- `GET /api/context/findings` (ungated read, like the ledger): the Teach-me shape (`profile`,
  `confidence`, `evidence`) per target, effects first then the closest misses by corrected p, plus
  **`effect_nights` of `nights`**: on how many of the last N runs (default 14, max 90) the candidate
  was an `effect`, so a one-night flicker reads as one. Filters `target`, `status`, `nights` are
  parameters, never formatted into SQL. Before the migration it answers `available: false`.

**Verified on a throwaway MySQL 8 (CI's recipe), container removed:** `alembic upgrade head` from
scratch to 0064; `downgrade 0063` (table gone); `upgrade head` again; `current --check-heads` =
0064. Then the real store and the real route against the real table, with rows from the screen over
three consecutive nights: 23 rows a night, a same-night re-run replaces (3 nights, not 4), an old
row is pruned, the API returns the planted effect first with `effect_nights` 3 of 3, and the status
and target filters work. 1,000+ unit tests cover the same paths with mocks. (That was before deployment.)

**Production backup (taken and verified, read-only):**
`/home/alfr3d/db_backups/alfr3d_backup_20261119_141508_pre_0064.sql.gz`, 40,463,020 bytes, gzip
integrity OK, `Dump completed` trailer, 38 tables, `alembic_version = '0063'`, no
`sa_covariate_findings` yet (`--single-transaction --routines --events --triggers`, as
`db_backup_daily.sh`).

**Plan on production (nothing run yet):** 1. Merge (CI green). 2. NUC: fast-forward to `main`; a
fresh `_pre_0064` dump if the one above is more than a few hours old. 3. `docker compose build
migrate sa-learner service-api`, `docker compose --profile test run --rm migrate` (0063 to 0064:
one empty table), `up -d --no-deps sa-learner service-api sa-awareness`. 4. Verify `alembic current`
= 0064, `SHOW CREATE TABLE`, run the stage once (`learner.run_discovery_screen()`), then
`GET /api/context/findings` shows `available: true` with 3 targets. 5. **Rollback:** `alembic
downgrade 0063` (drops the one table; the stage then logs and carries on) or restore the dump.
Risk: low. Needs from the owner: a go to run step 3 on the NUC.

## Deployed 2026-11-19 (owner's go; migration 0064 run on production)

Backup `_pre_0064` (14:15 local, 6 minutes before the run, verified as above); `main` (3d3046a4)
fast-forwarded on the NUC; `migrate` ran `0063 -> 0064`; `sa-learner`, `sa-awareness` and
`service-api` rebuilt and restarted, all healthy, logs clean. `alembic_version` = 0064.

**Verified live:** the stage run once by hand stored 23 rows (guests_home 8, house_empty 7,
away_minutes 8), all `insufficient_evidence` with the reason "the feature has no data in the lake
yet", and `GET /api/context/findings` returned `available: true` with 3 targets. That is the
honest result today: the production lake has no `context_features` file until the first nightly
build on the new code (03:30 UTC), which is when the screen sees real features. **Not yet
verified live:** a night with real candidate data, and `effect_nights` above 1 (it counts from the
first real night). Rollback unchanged: `alembic downgrade 0063` or restore the dump; not needed.
