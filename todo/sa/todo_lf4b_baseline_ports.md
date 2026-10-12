# LF-4b / LF-5a: event-stream rates, and the legacy baselines ported to learners

> **Layer:** L1 learners + first L2 · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-4, LF-5 · **Follows:** [todo_lf4a_scalar_learner.md](todo_lf4a_scalar_learner.md)

## Status: 🟡 Learners deployed 2026-10-10 and running in SHADOW beside every legacy rule. No rule has been cut over yet; that waits for a week of shadow data.

## What exists

| Learner | Module | Replaces | Output |
|---|---|---|---|
| Scalar series | `learners/scalar.py` | SA-9 `climate_deviation`; SA-2 attention median (`attention_focus`, `wind_down_signal`) | z, tail p, surprise, confidence per numeric series; attention series on a log scale |
| Event-stream rates | `learners/rates.py` | nothing legacy (new: email volume, notification bursts, track plays, routines, per-sender daily counts) | negative-binomial tail p per window, high or quiet |
| Device rhythm | `learners/device_rhythm.py` | `rhythm_break_anomaly`: `unusual_hour`, `expected_absent`, `still_on_past_typical` | availability p (per device, dow x hour) and session-length survival p |
| Presence | `learners/presence.py` (LF-3) | SA-3 `departure_anomaly` (the "still home when usually out" half) | already scores home as well as away |
| Household day | `learners/household_day.py` | SA-10 `household_unusual_day` | **layer-2** inference: Fisher's method over two features, weighted by their confidence, parents attached as evidence |

`sa/shadow.py` runs after the legacy rules each awareness cycle and logs
`SHADOW <rule> AGREE|DIFFER: legacy=... learner=...` only when the pair changes. Learner findings
are written to `sa_inferences`. Nothing in it can reach a card (every comparison is isolated).

## Measured

- **Rates (14-day walk-forward):** 4 windows flagged across all hourly streams at P <= 1e-4, e.g. 20
  notifications in an hour where 1.4 were expected, 6 routine runs in an hour. 52 profiles: 9
  event/email streams and 43 senders.
- **Device rhythm (14 days, 33 devices):** 2.1 % of device-hours reach the 3-bit surprise bar
  (about one per device every two days); the card gates (60 min offline, still in use, not
  replaced) are stricter.
- **Household day (v2, 50 backtested days, 08-15 to 10-11):** a third feature, `home_minutes`
  (person-minutes at home before 18:00 for owners' and residents' phones, silver's stay rule, live
  from `device_history` in shadow), and the rule is now "at least two of three features off".
  One day flags at P <= 0.01: **10-02**, when Munja was home 124 minutes against a usual 1,080
  and the device count followed. v1 flagged none. **10-09 (Athos out all day) is still not a
  household-unusual day** (p 0.998): the other residents were home, so the household total is
  normal. That absence is a per-person deviation, which the presence learner already scores (3.35
  bits); the household-day learner is the wrong place to catch it.
- **Attention:** `switch_count` on a log scale flags 16 of 242 hours at z >= 4 in 14 days (heavy
  use really is bursty); `unlock_count` flags none.

## Findings from the first shadow run

- Learner and legacy agree on all quiet rules (climate, attention, departure, household day).
- `rhythm_break_anomaly`: the legacy rule names one device; the learner names every device that
  is offline when it is normally on. Real ones (a Kindle offline four hours) and **identity
  churn**: a phone gets a new `device` row (MAC rotation), the old row stays offline while the new
  one is online. Fixed in shadow by skipping an offline row whose name is online under another id;
  the real fix, now in silver (2026-10-11): `device_identity` merges rows with the same name and the same owning person, and `device_sessions.device_id` is the identity (the most recently seen row), with `merged_rows` counting what was folded in. Names shared across owners (`iPhone`) or owned by nobody (`unknown`) are never merged. On the real lake it folds 8 named devices (Pixel-6a 4 rows, Littl3-Zen 4, leonardo 5, ...). Takes effect on the next silver build and learner fit; the shadow-side skip can be removed after one comparison.
- Devices not seen for 14 days, or offline for more than 3 days, are "gone", not "late", and are
  excluded from availability.

## Cutover checklist (per rule, after a week of shadow)

- [ ] `climate_deviation` reads the scalar inference instead of `entity_baselines` room rows.
- [ ] `attention_focus` / `wind_down_signal` read `attention:*` scalar inferences.
- [ ] `departure_anomaly` reads the presence inference (home, improbable).
- [ ] `rhythm_break_anomaly` reads device-rhythm inferences (device rows are now merged by identity in silver; deploy and refit first).
- [ ] `household_unusual_day` reads the layer-2 inference.
- [ ] Then delete `compute_entity_baselines` and the `entity_baselines` table (back up first).

## Not done

- Rates are fitted nightly and flag the last 48 h on each run; they are not scored live between
  fits. An hourly rates job would close that gap. Household day is scored live, once a day at 18:00
  local.
- Cards on rate deviations (email burst, notification storm) are a product decision, not built.
- Occasional-visitor learner (LF-5): parked, see [todo_lf5_more_learners.md](todo_lf5_more_learners.md).
  Drift detection is done (2026-10-11).
