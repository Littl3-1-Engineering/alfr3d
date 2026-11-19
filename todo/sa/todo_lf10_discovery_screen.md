# LF-10: discovery screen and derived targets (Context learning 4/5), PLAN

Status: **plan approved 2026-11-19.** Build order, each its own PR: (1) **target registry and
validation: built 2026-11-19** (`sa/targets.py`, `tests/test_sa_targets.py`); (2) nightly screen
`sa/screen.py` and its tests (not started); (3) migration 0064, the findings API and the
`learner.py` stage (not started; migration only after the backup and plan are shown). Decisions
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
