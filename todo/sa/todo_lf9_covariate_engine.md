# LF-9: shared covariate engine (Context learning 3/5)

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 3. Depends on LF-7
(replay, evidence) and LF-8 (context registry: which signals exist, with stable identity).

## What it is

One module, `services/service_sa/sa/covariates.py`, that answers "does this context signal explain
any of what this learner sees, beyond chance?" for any learner and any signal. It was extracted
from the scalar learner (LF-4a), the only place the test existed. No database, no lake access:
callers pass `(x, y, t)` pairs. No cards, no actuation.

- **Effect size:** Theil-Sen slope (median of pairwise slopes), subsampled past 400 points.
- **Held-out gain:** time-ordered 70/30 split; slope fitted on the first 70 %, judged on the last
  30 %: relative cut in the median absolute deviation. Never a fit judged on itself.
- `select(pairs, name, ...)`: the single-candidate test the scalar learner always used, kept
  exactly (sample floor `MIN_COVARIATE_HOURS` 72, gain floor `COVARIATE_MIN_IMPROVEMENT` 10 %).
- `screen(candidates, ...)`: the many-candidate version for discovery (Phase 4). Candidate
  feature x lag against one target, with a **budget** (`MAX_CANDIDATES` 8 per target; the rest are
  returned as `not_tested`, never silently dropped; the budget counts every candidate examined),
  **multiple-testing control** (a circular-shift permutation null, which keeps the feature's
  autocorrelation and destroys real alignment, gives an empirical p; Holm's step-down correction
  across every candidate examined), and a fixed seed so a night's run is reproducible. Each finding
  is `effect`, `insufficient_evidence` (with the reason) or `not_tested`; only `effect` is a result.
- `lagged_pairs(feature_by_time, target_by_time, lag_hours, step)`: builds the pairs for a lag
  (positive lag = the feature leads).

## Step 1 (this PR): extraction + scalar parity

The scalar learner now calls the engine; its `_select_covariate` only shapes the pairs.
`profile.params["covariates"]` (a list; today at most the one outdoor-temperature entry, same dict
as the existing `covariate` key) is added for the inspectable evidence the prompt asks for. No
`VERSION` bump: the fit is unchanged.

**Parity, two ways.** (1) `tests/test_sa_covariates.py` keeps a verbatim copy of the old
`_select_covariate` / `theil_sen` as the reference and asserts identical output over synthetic
cases (under the floor, no effect, strong effect, past the pair cap with gaps, near the threshold,
5 seeds each). (2) **Real data, read-only on the NUC** (2026-11-19): every scalar series fitted with
the deployed code and with the refactored module copies in the `sa-learner` container: 15 series,
15 identical (every pre-existing params key, `n_eff`, `stability`), only the new `covariates` key
differs. Verified live; the screen itself is unit-tested only (nothing calls it yet).

**Finding worth keeping.** Outdoor weather now has 321 to 862 hours of overlap with the series, so
the covariate test genuinely runs (the old docstring said "stays off: outdoor weather has existed
for a day"). On the sampled series (`attention:switch_count`, `attention:unlock_count`,
`deck:...:battery`) it did not clear the gain bar (improvement -0.05 % to -5 %): no weather effect
on those, recorded as "did not reduce held-out error enough", which is the honest outcome.

## Step 2: the covariate probe, and what it found (2026-11-19, read-only on the NUC lake)

`python -m sa.covariate_probe` (`sa/covariate_probe.py`) screens, per learner target, the residual
after the hour-of-week mean (a PROXY for each learner's own residuals) against the registry's
candidate features and lags with `covariates.screen`. It changes and registers nothing; it exists
to decide which learners earn an opt-in PR.

**Result: no effects, and mostly no power to find one.** 21 targets (11 presence people, 10 event
streams), 6 candidates each (outdoor temperature anomaly at lags 0 and 3 h, humidity, pressure,
calendar busy minutes at lags 0 and 1 h; the two forecast candidates had no data in the deployed
`context_hourly` yet, they arrive with tonight's rebuild). Zero `effect`s. But **16 of the 21
targets are at least 50 % zero** (all 10 event streams, 6 of 11 presence people), and on those the
engine's test is blind: a Theil-Sen slope is the *median* of pairwise slopes and the gain is a
*median* absolute deviation, so a mostly-constant target gives slope 0 and MAD 0, a gain of exactly
0.0 whatever the relationship. The probe now flags them `LOW POWER` rather than calling them "no
relationship". Only 4 presence targets (Elenka, Jenna, Munja, athos) were testable, and none
showed a gain over the bar. The strongest uncorrected gains (0.10 to 0.17 on one person's
temperature, pressure and humidity) did not survive the multiple-testing correction (p_adj 0.12 to
0.52), which is the correction doing its job. The day-level learners (stay, daytime, household day)
have one observation per day, 141 days of history: not testable.

**What this means for Phase 3.** (1) Nothing here justifies an opt-in PR for any learner today:
that is the "insufficient evidence, leave it alone" outcome the prompt asks for, recorded. (2) The
engine is the right tool for continuous targets (the scalar series) and the wrong one for the
learners' actual targets, which are binary, sparse or counts. Before Phase 4's derived targets
(time outdoors, guest counts) can be screened honestly the engine needs a **frequency-based**
effect measure alongside the robust slope: compare the outcome rate between feature terciles (or
present/absent for a binary feature) on the held-out final 30 %, with the same candidate budget and
the same permutation + Holm control. The prompt names "frequency counts" as an intended method.
That is the proposed next step (`screen_rates`), not built.

## Later steps (not started)

Other learners (presence, stay, daytime, household day, rates) opt in **one per PR, and only where
Phase 1's replay shows held-out gain**; otherwise record "insufficient evidence" and leave the
learner alone. Each opt-in PR carries a replay before/after, with no change to card counts or the
flag-day rate beyond what the replay predicted. `screen` is the Phase 4 (discovery screen) engine.

## Gotchas

- `screen`'s permutation null is the slow part (about `permutations` x `held_out_gain`); it only
  runs for candidates that already cleared the floor and the gain bar. It uses `max_pairs` 150, not
  400, for that reason.
- Lags are the caller's job (`lagged_pairs`); the engine does not know what a feature is. Season
  and month stay off until there is about a year of history (prompt, direction).
