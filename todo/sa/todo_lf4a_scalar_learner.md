# LF-4a: scalar-series learner (shadow of SA-9 `climate_deviation`)

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-4

## Status: 🟢 Learner deployed 2026-10-10 (`sa/learners/scalar.py`). Live scoring and the `climate_deviation` / `attention_focus` shadow comparison run in `sa-awareness` (persisted to `sa_shadow_comparison` since 2026-10-12). Cutover waits on the 2026-10-16 review; scoping the learner to the climate and attention series is still to do.

One learner for every numeric series in gold `scalar_hourly` (indoor temperature / humidity, Wi-Fi,
battery, speed tests, later anything). Model: hour-of-day effect + local 24 h level + robust (MAD)
sigma from one-step-ahead residuals, so a slow drift is not an alarm and a garbage reading
(a 1,800,000 ms ping) cannot inflate the scale. Output: two-sided tail probability, surprise bits and
the shared confidence. Series that describe HA's old home, constants and counters are skipped.
An outdoor-temperature covariate is wired in but stays off until it improves held-out error by 10 %
(weather in the right place has existed for one day).

## Measured (walk-forward, last 14 days, real lake)

| series | scored h | median abs z | p99 | flagged at z>=4 |
|---|---|---|---|---|
| indoor temperature | 319 | 0.82 | 4.4 | 6 (~3 / week) |
| indoor humidity | 319 | 0.66 | 2.6 | 0 |
| speedtest download | 169 | 1.01 | 4.0 | 2 |
| phone battery | 121 | 0.60 | 2.8 | 0 |

A normal has median abs z 0.67, so the scale is calibrated. `MIN_ABS_Z = 4.0` from this.

## Remaining

- [x] Live scoring in `sa-awareness` for indoor climate and attention (`shadow.py`, 2026-10-11).
- [ ] Shadow log beside `climate_deviation` for a week (running, persisted), then cut over and retire `entity_baselines` climate rows.
- [ ] Turn the covariate on when >= 72 h of Toronto weather overlap exists and it earns its place.
- [ ] Event-stream learner family (rates per context / sender) and the SA-2, rhythm, SA-3, SA-10 ports.
