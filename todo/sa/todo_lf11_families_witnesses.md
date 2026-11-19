# LF-11: declarative layer-2 families and weak witnesses (Context learning 5/5)

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 5. Builds on LF-6
(layer 2), LF-7 (replay, the evidence) and LF-8 (registry). Status 2026-11-19: **step 1 (family
registry) merged (#451), proven unchanged on real data; step 2 (witnesses) built and MEASURED: both
ship disabled, with the evidence below.**

## Step 1: the family registry (built)

`sa/families.py`: one `Family(name, signals, key_prefixes, role, quality, description)` per source,
replacing the dict (`FAMILY_BY_SIGNAL`) and prefix tuple (`FAMILY_BY_KEY_PREFIX`) that lived inside
`layer2.py`. `layer2.family_of` asks the registry; the two old names are still exported, derived
from it. A new sensor joins fusion by one registration and a validation run, with no `layer2.py`
edit. `validate()` rejects duplicate names, a signal or prefix claimed twice, an empty prefix, a
prefix that shadows another family's, an unknown role and a witness quality outside (0, 1].

**Proof that nothing changed.** (1) `tests/test_sa_families.py` keeps a verbatim copy of the old
mapping and lookup as the reference: the derived maps equal the old literals; 2,000 fuzzed
signal/key/evidence combinations agree with the old lookup; every old test of `family_of` still
passes untouched. (2) **Real data, read-only on the NUC:** the Phase 1 replay (`python -m
sa.replay --start 2026-08-20 --end 2026-11-17 --sweep`, all six reports) run with the deployed code
and with the new `families.py` + `layer2.py`: **byte-identical JSON** (away_unusual 22 flagged of
831 person-days, day_off 5 of 25, household_day 6 of 79, stay_profile 30 of 411, both sweeps). A
throwaway test sensor registers in one `Family(...)` and resolves, with no layer-2 change.

**Findings along the way.** The `climate` family (`esphome:` series) has no layer-2 rule reading it
today (no rule's `groups()` selects a climate parent), which is why the prompt could ask "which
rules use the climate family" and the answer is none. That makes it free to re-role as a witness
without changing any output.

## Step 2: weak witnesses (designed 2026-11-19, built and measured the same day; see "Step 2 results")

### What the data says about the two proposed witnesses (read-only, NUC, 2026-11-19)

- **Indoor ESPHome node** (one Athom temperature/humidity sensor): Temperature, Humidity, WiFi
  since 2026-09-16 (~1,380 hours); `Light`, `Power Button` and `Status` since 2026-10-10 (852
  hours). **Correction (same day): `Light` is a hand-toggled binary status LED, not an activity or
  light-level signal** (see "Step 2 results"); this bullet originally said otherwise, unchecked.
  Temperature and humidity move with weather and heating as much as with people. There is no room
  mapping, so the most it could say is that the house is busy.
- **Coarse Deck location:** `device_location_history` has 2,391 rows since 2026-09-11 from 4
  installs; one install carries 1,900 rows (median gap 23 minutes, 68 distinct days), another 431,
  the rest a handful. Accuracy is 2,000 m on all but three rows (provider `network` or `fused`, 111
  `gps` rows): a coarse "which 2 km cell" signal. The main install sits outside its most common
  cell on 50 of its 68 days (783 rows), so "away from the home cell" has real variation to
  measure, but at 2 km it can only separate "near home" from "clearly elsewhere".
- **How much can be measured:** the replay window (2026-08-20 to 2026-11-17) holds 22 `away_unusual`
  flag-days in 831 person-days. That is enough to see a gross effect of a witness on the flag
  count, not a subtle one; it is not enough to prove one helps. Said plainly so the result is not
  over-read.

### Mechanism (one change to `layer2.fuse`, off by default)

A `WITNESS` family never votes, never anchors and never creates a surprise. Each rule says which
witness rows apply to a group and in which direction (+1 corroborates the anchor's claim, -1
contradicts it); `fuse` then scales the **confidence** (never the probability or the bar) by
`1 + clamp(sum(direction x quality x row confidence), -CAP, +CAP)` with a small CAP (proposed
0.15). So a witness can only raise or lower the confidence of a surprise the voting families
already show, by a bounded amount, and a result with no witness rows is exactly what it is today
(the replay above is the guard). Witness rows are recorded in the result's evidence so the owner
can see what moved the confidence.

### The two witnesses (the design as first written; superseded where "Step 2 results" says so)

1. **`indoor_activity`** (the ESPHome node): re-role the `climate` family as a witness, quality
   about 0.3; evidence is a fresh scalar deviation on the Light series (and only that, to start),
   applied to the **household-level** rules (`day_off`, `household_unusual_day`) where "the house is
   busy" is the right claim, not to person-level `away_unusual` where it is not (no room mapping).
2. **`deck_location`** (coarse): a new witness family, quality about 0.3, from a layer-1 state row
   "away from the home cell by more than 5 km" per install owner; applied to `away_unusual` as a
   corroborating witness (agrees: confidence up; at home: confidence down). It reads the coarse
   rows only, the same data the owner already shares.

### Measurement and the ship rule

Replay (Phase 1) with each witness on and off, same window: flag-day rate (must not move: a
witness cannot create or remove a flag) and the confidence of the 22 flag-days, split by whether
the person was in fact away (from the presence grid, the same ground truth the replay already
uses). **If a witness does not raise confidence on true absences or lower it on false ones, it
ships disabled** and the doc says so. The prompt allows exactly that outcome.

## Precise location: a proposal, not a change (waiting for the owner's decision)

The Deck owns location capture and this prompt says not to change precise-location behaviour. If a
precise (GPS-grade, a few metres) signal is ever wanted for learning, the proposed design is:

- **Opt-in per install**, off by default, with its own plain-language consent screen (what is
  collected, that it stays in the household, that it can be reset), separate from today's coarse
  opt-in. Foreground-only capture stays the rule unless a separate consent says otherwise.
- **Registered as `precise_location`, privacy `restricted`** (it already is): visible in the
  ledger, never built into `context_features`, never offered to a learner (enforced in
  `context_registry.learner_candidates` and `targets.validate`). The owner opens it explicitly per
  feature (`owner_opened`), and closing it deletes what was derived from it.
- **Derived, not raw, if opened:** a learner would see "distance from home bucket" or "arrived /
  left", never coordinates, and never an individual trace in any API.
- **Resettable and inspectable:** one reset clears the install's precise rows and everything
  learned from them; the Teach-me view lists what is derived.

Nothing in this PR touches capture. Decision needed from the owner: whether to pursue this at all.

## Open design questions for the owner

1. Is applying the ESPHome witness to the household-level rules only (not `away_unusual`) right?
2. Is a confidence-only effect with a 0.15 cap the right size, or should the cap be tighter?
3. Pursue the precise-location opt-in above, or leave location coarse?

## Step 2 results (built and measured 2026-11-19): both witnesses ship DISABLED

**Mechanism (built, off by default).** `families.Family` has a `WITNESS` role and a `quality`;
`layer2.Group` takes `witnesses=[(row, CORROBORATES | CONTRADICTS)]`; `layer2.fuse` ignores a witness
family when voting and, **only if the rule lists the family in `Rule.witness_families` (empty by
default)**, scales the result's confidence by `1 + clamp(sum(direction x family quality x row
confidence), -0.15, +0.15)`. It never touches the probability, the surprise or the 3-bit bar, so it
cannot create or remove a surprise; the rows that moved a result are recorded in its evidence
(`witnesses`). With witnesses off, output is byte-identical (the six default replay reports match
the pre-change baseline exactly on the real lake). Tests: `tests/test_sa_witnesses.py` (a witness
off changes nothing; far raises and near lowers by quality x confidence; surprise and probability
never move; a weak surprise is not created; the cap holds; a witness with no confidence says
nothing; a witness family never votes; a rule hears only the families it lists).

**Witness 1, the indoor ESPHome node: NO BASIS, not registered.** Correction first: an earlier
version of this doc said the node's **Light** series was the closest thing to an activity signal.
That was wrong and I had not looked at its values. `Light` is a binary entity (on in 168 of 852
hours); it flipped 6 times in 38 days, with runs of 135, 19 and 18 hours spread evenly across the
hours of the day, i.e. a status LED toggled by hand, not ambient light and not activity. `Power
Button` and `Status` are constant. The scalar learner correctly has profiles only for Temperature,
Humidity and the two WiFi series. So the question became whether the node's temperature or humidity
carries any occupancy signal. Measured with the Phase 3 screens (read-only, real lake): against
`house_empty` (rates) and `away_minutes` (slope), temperature and humidity as weekly anomalies and as
hourly change, at lags 0 and 1: **no candidate clears the held-out gain bar** (best: humidity
anomaly at +1 h, gain 4.3 %, corrected p 0.12, against `house_empty`). The node is one sensor in
one room with no room mapping, which is also why it could not have said more than "the house is
busy". An ESPHome witness is therefore **not registered**: re-roling the `climate` family as a
witness was tried and reverted (existing `fuse` tests use ESPHome series as ordinary voters, so
the family must stay a voter), and the measurement says there is nothing for a witness to say.

**Witness 2, the coarse Deck location: registered, measured, disabled.** New family
`deck_location` (witness, quality 0.3), observer `learners/deck_location.py`: a layer-1 state row
`far` (at least 5 km from home), `near` (within 2 km, the fix's own uncertainty) or nothing (between,
stale after 45 minutes, no home, no fixes), row confidence 0.4 so one witness moves confidence by at
most 0.3 x 0.4 = 12 % and the 15 % cap binds only when several agree. `away_unusual` offers it to
every group (far corroborates, near contradicts) but does not enable it. Replay on the real lake
(`python -m sa.replay --start 2026-08-20 --end 2026-11-17 --witness-location`, read-only; home is
each install's most common place, a stand-in for the backend's configured coordinates):
- it spoke on **12 of 142** presence deviations (6 far, 6 near); it created or removed no result;
- confidence raised on 6, lowered on 6, **mean change -0.0005**;
- it dropped **1 result under the card-confidence bar** (1 of 22 flag-days); it added none. The
  earlier claim that a witness "cannot change the flag-day rate" was wrong: "flagged" in the replay
  means it reaches a card (surprise and confidence), so a witness that lowers confidence can move a
  result across the bar. That is bounded and visible, and now counted, but it is a real effect;
- **agreement with an independent family** (the Deck's own network state) is where a witness is
  validated, and the data cannot do it: only 3 anchor hours had both (2 agree, 1 disagrees), none
  with Deck wifi.
It does not show that the witness helps, so by the rule in this doc it **ships disabled**: no live
rule lists it, no live row is written (`shadow` does not produce `deck.location`), and nothing is
deployed that changes behaviour. Revisit when more installs report, or more overlap with Deck
network state exists to validate it against (the replay command above reproduces the measurement).

## Decisions (owner, 2026-11-19)

- **Precise location: keep it coarse.** The coarse 2 km signal already separates "near home" from
  "clearly elsewhere". Precise would add a second permission prompt, a Play data-safety change
  (a human step in Play Console), new disclosures and some battery cost, for no measured gain.
  Revisit only if a concrete learner (for example layer-3 arrival anticipation) shows coarse is not
  enough. Nothing in the Deck changes.
- The witness design above (confidence-only, capped at 0.15, ship disabled unless the replay shows
  help) was approved; the replay did not show help, so both ship disabled.
