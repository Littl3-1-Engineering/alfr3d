# LF-7: Replay harness and layer-2 calibration (Timeline "Context learning 1/5")

Layer: tooling for L1 and L2 | Roadmap: [SA_ROADMAP.md](SA_ROADMAP.md)

Status 2026-11-19: **slices 1 to 3 built, in progress**. Slices 1 and 2 (replay harness, parity
script, the stay-arrival fix) merged in PR #422 and deployed to the NUC on 2026-11-18. Slice 3
(branch `feat/sa-parity-coverage`) adds the Deck family to the replay and parity for the scalar,
rate and device-rhythm learners. The stay parity re-run waits for days after the deploy.

## What exists

`services/service_sa/sa/replay.py`, run with `python -m sa.replay --days 28 --sweep` (or
`--start D --end D --only away_unusual day_off`). Read-only: it opens the lake and nothing else
(a test fails if it opens a network connection). It wraps the learners' existing walk-forward
`backtest` functions (each day scored by a model fitted on earlier days only) under one report
format, per rule and per window:

`name, kind, window, evaluations, flagged, observed_days, flag_days, flag_days_per_14,
target_per_14, by_subject, unreconstructed, method`

A flag-day is a local day with at least one result at or above the 0.3 card confidence floor.
`flag_days_per_14` is flag-days per 14 observed subject-days (person-days; one household-day for
`household_unusual_day`), so a person rule and the household rule read on the same scale.

Replays registered: `away_unusual`, `day_off`, `household_unusual_day` (layer 2) and `stay`
(layer 1, the source of the `departure_anomaly` card).

## What history cannot give back (declared on every report, never invented)

- **Calendar free/busy**: purged after each event, no per-day history. `day_off` is replayed under
  three calendar states (unknown, empty day, booked day) so the bounds are visible. The 70 %
  calendar discount (`Rule.explained_discount`) only acts when an event covers "now", so it
  **cannot be measured at all** until free/busy history is kept (parallel capture track).
- **Deck network family**: history starts 2026-10-11 for two installs and is not joined to the
  replay yet, so the Deck-family floor is **not calibrated** in this slice.
- **Owned-device parents** of `away_unusual`: no owner map in the replay, so `away_unusual` is the
  presence-only floor of what the live rule flags.

## First measured result: window 2026-10-22 to 2026-11-18 (28 days), NUC lake, read-only

| rule | flag-days / observed person-days | per 14 | note |
|---|---|---|---|
| `away_unusual` | 1 / 264 (10 users) | 0.05 | the one flag is user 1 (Athos) |
| `day_off` | 1 / 14 (2 users with enough history) | 1.0 | calendar bounds: unknown 1, empty 1, booked 0 |
| `household_unusual_day` | 1 / 23 | 0.61 | bar already self-calibrated to about 1 in 14 |
| `stay` (L1) | 5 / 108 (4 users) | 0.65 | all 5 are user 1; **hindsight number**, see Resolved below |

`day_off.corroboration_floor` sweep over 0.3, 0.5, 0.7, 1.0: 1 flag-day at every value, so the
0.3x factor is **not sensitive on this data** (the one flag has high confidence). **No constant is
changed**: with one event per rule the observed rates cannot support a different value, and the
calendar discount and Deck floor cannot be measured here. Revisit when more flags exist or once
calendar free/busy history is kept.

## Resolved 2026-11-19: the `stay` replay-vs-live mismatch (not a defect, and not the drift cap)

The mismatch was between two different windows and two different bridge settings.

1. **Windows did not overlap.** The replay covered 28 days (10-22 to 11-18); the shadow review's
   "0 episodes at confidence >= 0.3" covered 14 (11-05 on). Live `sa_inferences` for user 1 do
   hold >= 0.3 episodes in the earlier part (10-21/22 0.303, 10-22 to 10-24 0.33, 10-25/26 0.318,
   10-25 to 10-28 0.35; stored value is the last upsert, not the peak).
2. **On the shared window the two agree.** 11-05 to 11-18: the replay fires on one day (11-05) at
   stability 0, so confidence 0, and live shows no episode >= 0.3. Both 0.
3. **Before 11-01 the replay cannot reproduce live, by construction.** Silver is rebuilt with the
   learned per-person bridge (PR #365, deployed 2026-11-01) over the whole lake, so Athos's
   10-25 to 10-28 stay, one 3-day stay for live under the fixed 45 min bridge (conf 0.35), is four
   stays of 23-24 h today (gaps of 104, 43 and 68 min), none unusual. The 62.7 h stay 10-28 to
   10-31 exists only in today's silver, which is why the replay flags 10-29 and 10-30 and live then
   did not (its stay ran 10-27 22:47 to 10-31 at confidence 0.197). 10-22 to 10-24 agree.
4. **The drift cap hypothesis is rejected as the cause.** Live stability for user 1 is 0.96 (not
   capped), and every day-level difference above traces to the intervals.
5. **Minor, not verified:** live stored a 5.58-bit episode 11-10 to 11-12 at confidence 0.201
   (below the card floor, so no flag-day either way); the replay samples at hh:30 and ends before
   that stay's last sighting, so it may simply not reach the tail. Irrelevant to flag-days.

Consequences. The replay answers "what would today's code say", and the `stay` report now says so
(`unreconstructed`). The "5 flag-days, user 1, 2.6 per 14" figure above is a hindsight number:
do not read it as the live rate (live published 0 `departure_anomaly` cards in the last 14 days).
A parity check is only meaningful on days after the inputs match (silver and profiles built by the
deployed code), so it should compare stored `sa_inferences` with a replay over days since the last
change to a learner or to silver, not across a deploy. That needs the database, which this
harness deliberately does not open, so parity is a separate script.

## Parity script (slice 2): `python -m sa.parity [--since D] [--only learner ...]`

`services/service_sa/sa/parity.py`, read-only (lake and database reads, no writes), run inside
`sa-learner`. For every stored profile it walk-forward replays each day since `--since` on a
15-minute grid (a profile refitted from the lake through the day before, as live's nightly fit
would have), compares it with the stored live inferences per (learner, subject, local day), and
re-fits the stored profile from the lake as of its `fitted_to` to check n_eff, coverage, source
quality and stability. Verdicts pool subject-days per learner and read INSUFFICIENT below 14.

Design decision recorded because the first attempt was wrong: comparing "days after the stored
profile's `fitted_to`" can never work, because the lake only gains day D at the nightly build that
also replaces the profile live used on D. Profiles are not versioned, so the profile is rebuilt from
the lake instead. That rebuild equals live's only while the lake's inputs are unchanged, so the
comparison starts at `MATCHING_INPUTS_SINCE` (2026-11-01, the learned presence bridge); advance it
after any later learner or silver change, never backwards.

### First run: 2026-11-01 to 2026-11-17, NUC lake and database

| learner | verdict | both / live-only / replay-only / neither (subject-days) | card-floor flips |
|---|---|---|---|
| `presence_profile` | MISMATCH, 2 days | 17 / 1 / 1 / 151 | 0 |
| `stay_profile` | MISMATCH, 19 days | 6 / 18 / 1 / 77 | 0 |
| `daytime_profile` | MISMATCH, 3 days | 9 / 1 / 2 / 158 | 0 |
| `household_day` | MATCH | 1 / 0 / 0 / 16 | n/a (bar-gated) |

- **presence:** scores agree to about 0.01 bits on most shared days (user 9: 14 shared days, live
  and replay bits within 0.02). The two one-sided days (user 1 on 11-09 replay-only at 3.20 bits;
  user 6 on 11-01 live-only at 3.12 bits) both sit within 0.2 bits of the 3-bit bar; consistent with
  a bar crossing between live's 60 s cycle and the 15-minute grid, **not verified**. Replay
  confidence is higher than live's (user 9: 0.21 against 0.13): the drift cap on stored stability
  (users 1, 6, 9, 10 are drift-capped), which is expected and labelled by the profile check.
- **household_day:** the one flagged day (11-14) agrees (6.84 bits live, 7.17 replay). The earlier
  "11-15 live-only" was an attribution artifact (row refreshed just after midnight); fixed by
  crediting day-keyed rows (daytime, household day) to their start day only.
- **daytime:** 3 one-sided days, not investigated. Scores differ on shared days (user 6, 11-10:
  3.29 live against 5.11 replay) because a stored row holds the last checkpoint's value while the
  replay keeps the strongest of the day's checkpoints; a method limit, not evidence of a bug.
- **stay: a real live bug, root cause found and fixed in this branch (not deployed).** 18
  live-only days, almost all users 6 and 9. Live stored stay rows ran about 24 h (`stay_minutes`
  1,340 to 1,696) with the right start but a `window_end` at the person's *next arrival*. Example,
  user 9 (Vanja): live row 2026-11-04 20:25:26 to 11-05 20:29:22 (1,444 min); silver stay ended
  13:45:02. **Cause:** `device_history` logs the *previous* `last_online`, so the row stamped
  20:28:38 on 11-05 carries `last_online` 13:45:02, and the new sighting (20:28:38) only becomes
  readable in the next row (20:29:44). `user.state` flips to online at once (the `came_online`
  event is 20:28:39), so for a cycle or two after every arrival `shadow._stay_start` rebuilt the
  stay from the newest readable sighting, which was the previous stay's last one, and scored that
  old stay as lasting until now. Every arrival after a long absence produced one spurious
  ~24 h-stay row (users 6 and 9 daily, user 1 after multi-day stays; the 11-10 to 11-12 Athos row I
  could not explain earlier is the same thing). **Fix:** `_stay_start` returns None unless the
  newest sighting is within `LIVE_OFFLINE_LAG_MINUTES` (31) of now, the rule `user.state` and the
  replay's `stay.current_stay_start` already follow. Regression test
  `test_arrival_before_the_new_sighting_is_logged_does_not_score_the_previous_stay` fails without
  the fix; the old departure fixture encoded the bug (newest sighting 10 h old, still expected a
  flag) and now uses a phone seen up to the evening. **Impact before the fix:** no card. Stored
  confidence was 0.0 to 0.2 for every stay row since the 11-01 cutover (0 rows at or above 0.3),
  and the only `departure_anomaly` cards ever shown were the legacy ones on 2026-09-12. It would
  have produced a false "hasn't been out in 24 h" card for anyone whose stay profile reached 0.3
  confidence. **After deploying, advance `parity.MATCHING_INPUTS_SINCE`** to the deploy date: live
  behaviour changed, so earlier days no longer compare.

## Slice 3: one-sided days explained, Deck family, three more learners (2026-11-19)

**Presence and daytime one-sided days.**
- Parity now starts at a **per-learner** date (`parity.MATCHING_INPUTS_SINCE`): the learned bridge
  (PR #365) was deployed *during* 2026-11-01, so that day's live profile was fitted before it (user
  6, 11-01: live 3.12 bits against 2.99 replayed). Presence, daytime and household start 11-02; the
  stay learner starts 11-19 (the arrival fix); rates 11-16 (now-playing de-duplication halved
  `play_start` rates at the next refit); device rhythm 11-15 (day-type stability).
- A one-sided day whose flagged score is within 0.5 bits of the bar is `borderline`, reported and
  never hidden: the nightly silver rebuild re-derives history with the bridge learned that night, so
  the same day scores a little differently live than from today's lake.
- Presence 11-02 to 11-17: **MATCH**, 16 shared flagged days, 1 borderline (user 1, 11-09: replay
  3.2 bits, live nothing). That day is explained by a live-data gap, not a learner: `user.state`
  never flipped offline for anyone in three windows (about 14:05 UTC 11-07, 20:00 UTC 11-08, 11:21
  UTC 11-09; no `went_offline` event for users 1, 6, 9 or 10, and the event stream is silent in the
  11-09 window), while the phones were unseen for 2 to 9 hours. Clean since 11-09 (every later
  phone gap has its event). The cause in `service_user` is not found; the logs for those days are
  gone.
- Daytime 11-02 to 11-17: 8 shared, 2 borderline, **1 mismatch** left (user 6, 11-03, replay-only,
  3.55 bits, confidence 0.14, below the card floor), 0.05 bits past the tolerance band. Not
  explained; left flagged and not tuned away.
- Household day: MATCH (the one flagged day, 6.84 live against 7.17 replayed).

**Deck family reconstructed** (`replay.load_deck`, `replay.deck_state_at`, from bronze
`deck_context_history` and the install-to-user link on `device_location_history`; two users have a
reporting Deck). `replay_away_unusual` now runs the real rule with Deck states and
`--sweep` varies `explained_discount` (only the Deck's wifi state explains in a replay, so this
calibrates that discount without touching the calendar's). Over 2026-10-22 to 11-18: 11 presence
deviations in total, **none coincided with a sustained Deck state**, so the Deck family changed no
flag (1 flag-day with and without it) and the discount sweep (0.5, 0.7, 0.9) is flat. **Not
calibratable on this data; no constant changed.** By design a very surprising absence survives the
default 70 % wifi discount (a test pins it).

**Parity for scalar, event_rate, device_rhythm** (`parity.COVERED` is now a per-learner spec: replay,
subject key, observed days, live-row filter, subject selection). Only subjects live actually scores
are compared (scalar: the ESPHome temperature and humidity and the two attention series; rates:
hourly event streams; device rhythm: not household hardware); the rest have only the nightly 48 h
batch and are reported under `not_compared` with the reason. Nightly batch rows are filtered out.
Run 2026-11-19, 11-02 onward (rates 11-16, devices 11-15):
- **event_rate:** MATCH on quiet days only (8 live-scored streams, 2 days, neither side flagged).
- **scalar_baseline (live-scored series), after the band fix below: 12 shared days, 11
  borderline, 4 live-only, 0 replay-only.** The first reading ("11 mismatches, hypothesis: live
  scores a snapshot against an hourly-mean profile") was **checked and the hypothesis is not
  supported**:
  - The units do differ, as suspected: the Deck's counters reset after every report
    (`AttentionTelemetryStore`), so live scores the latest single report's count, while the lake
    series and the profile are the hourly mean of those reports (`silver_contexts`: AVG per hour).
  - But single reports are *not* more extreme than hourly means under the stored profile (z over
    11-02 to 11-18, trailing level supplied as live does): the share at or over the 4-sigma bar is
    7.0 % for single reports against 7.3 % for hourly means on `switch_count`, and 0.3 % against
    0 % on `unlock_count`. So the scoring unit does not inflate flags. The 4 remaining live-only
    days are single reports that crossed the bar while their hour's mean did not, which is that
    unit difference and nothing worse.
  - The near-bar band was wrong for z-based learners: 0.5 bits is a sliver where the 4-sigma bar is
    about 14 bits and half a sigma is about 3. The scalar band is now half a sigma
    (`NEAR_BAR_Z`), which turned 7 false mismatches into borderline days.
- **FINDING: `attention:switch_count` is badly calibrated, steadily.** Walk-forward over
  2026-10-12 to 11-18 it crosses the 4-sigma bar in **6.4 % of hours** (53 of 833; 3 to 14 per
  week of about 160, every week), against about 0.006 % for a 4-sigma bar on a Gaussian: the series
  is spiky and heavy-tailed and the robust sigma (0.28 in log units) understates the tail (p95 of
  |z| is 4.5, p99 is 7.8). The module's docstring says `MIN_ABS_Z` "was chosen from the backtest's
  actual false-alarm rate"; for this series that does not hold today. The other live-scored series
  are fine: `unlock_count` 0 % (p99 3.1), ESPHome temperature 0.9 % (7 of 787), humidity 0.1 %.
  Effect: the series produces flag episodes almost daily (the `attention_focus` card is held to
  3.5 a week by its own budget, not by the model). **Not changed here** (it would change what
  cards fire). Proposed fix for a decision: calibrate the bar per series from the walk-forward
  |z| distribution (for example the z that gives at most one flag a week) instead of one global
  `MIN_ABS_Z`, and re-run this replay before and after.
- **device_rhythm: 9 replay-only days, APPROXIMATE replay.** The live rule reads the `device` row's
  state and last_online; the lake has sessions, so online/offline is approximated (online until 31
  minutes after a session's last sighting). Replay flags device 4 (Athos's phone) for most of the
  day on 11-15 to 11-17 (52 to 80 flagged grid times) while live flags nothing, which says the
  approximation is wrong for that device, not that live is. **Not evidence about live.**

## Remaining for this phase

- [x] Replay-versus-live parity script. Covers presence, stay, daytime, household day, scalar, event
      rate and device rhythm (approximate); not drift.
- [x] Cause of the stay discrepancy found and fixed, deployed 2026-11-18 (PR #422).
- [x] Presence and daytime one-sided days looked at (above): one live-data gap, one tolerance band,
      one bridge deploy date, one daytime day left unexplained.
- [x] Deck family reconstructed; its discount cannot be calibrated yet (no overlap in the data).
- [ ] **Stay parity re-run** once the lake holds a few days after 2026-11-19 (needs 14 person-days:
      6 profiles, so 3 days). Expect the live-only stay days to stop.
- [x] Scalar hypothesis checked and refuted (above); replaced by a measured finding.
- [ ] **Decision needed:** per-series calibrated bar for `attention:switch_count` (6.4 % of hours
      flagged at the global 4-sigma bar). Not implemented; it changes live cards.
- [ ] Device-rhythm replay: reconstruct the `device` row state properly (from `device_history`,
      which has per-scan state) instead of from sessions.
- [ ] Find why `service_user` emitted no `went_offline` for any user in three windows (11-07 to 11-09).
- [ ] Re-run parity for the Deck family once Deck states overlap presence deviations; re-run the
      `explained_discount` sweep then. Same for the calendar discount once free/busy is kept.
- [ ] Notion and `timeline.json` follow each merged PR.
