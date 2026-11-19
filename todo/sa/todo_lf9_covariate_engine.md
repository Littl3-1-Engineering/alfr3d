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

**What this meant for Phase 3.** The engine's slope test suits continuous targets (the scalar
series) and was the wrong tool for the learners' real targets, which are binary, sparse or counts.
That became step 3.

## Step 3: `screen_rates`, the frequency-based screen (2026-11-19)

`covariates.screen_rates` is `screen` for binary and count targets, on the same scaffold (`_screen`:
candidate budget, sample floor, held-out final 30 %, circular-shift permutation null, Holm
correction, fixed seed, the same three statuses). The question is asked in frequencies: **within
the same cell (hour of week, chosen by the caller), is the outcome more or less common when the
feature is in its top third than in its bottom third?** Fitted on the first 70 % (cell means, then
the extra rate per feature tercile), judged on the final 30 % by how much the feature's offset
reduces the squared error of the cell-mean prediction. The effect reported is `rate_shift`
(outcome per hour, top third minus bottom third; a binary feature uses its two populated buckets).
It needs `RATE_MIN_EVENTS` (20) non-zero outcomes: a rate cannot be estimated from a handful of
events, so under that floor the answer is insufficient evidence, not a rate. The gain bar is 1 % of
held-out squared error (`RATE_MIN_IMPROVEMENT`), lower than the slope screen's 10 % because the
permutation + Holm test is the real guard against false positives, not the bar.

**Tests** (`tests/test_sa_covariates.py::TestScreenRates`): a planted rate shift is found on data
where the slope screen returns a gain of exactly 0.0 (the two screens side by side); planted nulls
not found (6 seeds); 8 independent null candidates give 0 effects; the real candidate survives
beside a decoy; hour-of-day structure is not mistaken for a feature effect; too few events is
insufficient evidence; budget and reproducibility; a binary feature with random-length runs. Two
things the tests taught: the circular-shift null correctly cannot separate a strictly periodic
feature from its own shifted copy (so tests use random-length runs, and a real exactly-periodic
feature would behave the same); and a feature that drifts (a random walk) leaves its training range
in the held-out window, so features should be stationary anomalies, as the probe's are.

**Probe re-run on the real lake (read-only, 2026-11-19), sparse targets now via `screen_rates`:**
24 targets (11 presence people, 10 event streams, 3 email streams), 6 candidates each, **0 effects**.
The 19 sparse targets, now genuinely tested rather than blind:
- **Too few events to say anything** (floor, not "no relationship"): `iot/device/set` (0 to 8
  events), `presence/user/entered_area` (11 to 19), presence for Biljana, Gorango, Kuma (0 to 9)
  and mostly Predrag and Vesna.
- **Tested, no gain over the bar:** `info/user/came_online`, `iot/device/turned_on`, `called`,
  `messaged`, `went_offline`, `email/promotions` (best gains under 1 %).
- **Closest to something, still not an effect:** `audio/track/play_start` (best gain 4.6 %, p_adj
  0.06), `presence:Vanja` (4.4 %, p_adj 0.24), `routine/executed` (1.9 %, p_adj 0.12),
  `email/updates` (2.1 %, p_adj 0.12). `play_start` at 0.06 is the one to re-run as history grows.
- The 4 dense presence people (Elenka, Jenna, Munja, athos) still go through the slope screen: none.

**What this means.** No learner earns an opt-in PR today ("insufficient evidence, leave it alone"
is the recorded outcome), but the screen can now actually see a rate shift, which it could not
before. The forecast candidates (`forecast_temp_c`, `forecast_rain_probability`) had no data in the
deployed `context_hourly` yet; re-run after the nightly rebuild that includes them. Next: Phase 4's
derived-target registry and the nightly screen both build on `screen` / `screen_rates`.

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

## Correction (2026-11-19, same day, found while building Phase 4 step 2): three flaws in the probe

The Step 2 and Step 3 "0 effects" results above were produced by an engine and a probe with three
flaws, found when the nightly screen (LF-10) first ran on the real lake and reported five strong
"effects" that did not survive scrutiny. The conclusions "no learner earns an opt-in PR" and "closest
is `audio/track/play_start` p_adj 0.06" are withdrawn as stated; the corrected picture is below.

1. **Permutation resolution made an effect impossible.** With B permutations the smallest possible
   p is 1 / (1 + B), and Holm multiplies it by the number of candidates looked at: 99 permutations
   and 8 candidates give 8 / 100 = 0.08 > 0.05, so no candidate could ever be an `effect`. The
   probe's `play_start` "p_adj 0.06" was 6 x the minimum possible p, not a near miss. Fixed in
   `covariates._screen`: B is raised to `ceil(candidates / alpha) - 1` and recorded on each finding;
   the default is now 199. A test planted an enormous effect (shift 0.39) and showed it returning
   "insufficient evidence" before the fix.
2. **The weather anomaly kept the autumn cooling trend.** Measured against the whole-history mean
   for that hour of day, temperature still drifts over ~40 days; any outcome that also drifts then
   looks caused by it. With flaw 1 fixed, the screen reported five effects (guests_home x 3,
   house_empty x 2 against the temperature anomaly, held-out gain up to 0.23). Re-measured with the
   anomaly taken against the **previous 7 days at the same hour** (causal, full window), all five
   vanished: nearly all the guest-hours in the weather overlap were in its first week. That
   definition is now `screen.anomaly_vs_trailing_week` and the probe uses it. A test plants a
   shared drift (cooling temperature, increasingly frequent guests, no causal link) and requires
   no effect.
3. **Sparse overlap.** After the first week is dropped, the real weather overlap holds 2 guest-hours
   and 18 empty-house hours, under the 20-event floor: `insufficient evidence`, the correct answer.

**Re-run with all three fixed** (real lake, 24 targets x 6 candidates): 3 borderline "effects" at a
corrected p of exactly 0.05 (`email/all` and `notification/sender/messaged` against the temperature
anomaly, held-out gain 1.3 % to 2.1 %). At a 5 % family-wise level across 24 targets about one false
positive is expected, so these are not evidence; they are what the nightly screen's "closest
candidates" list is for. **No learner earns an opt-in PR on this evidence.** The honest lesson is
that the per-target error rate multiplies across targets and across nights, so a real result should
be seen on several nights before it is believed (a proposal for the findings API: show the number of
recent nights a candidate was an `effect`).
