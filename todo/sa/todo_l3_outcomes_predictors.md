# Layer 3, items 1/4 and 2/4: outcome labels and the predictor registry (Phase 6a, 6b)

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 6; design page
"Layer 3: anticipation with earned autonomy". **Design and read-only measurement only: nothing here
acts, creates a card, or can reach a device.** Evidence inventory: `todo_l3_outcome_evidence.md`.
Status 2026-11-19: 6a and 6b built and measured on the real lake; 6c (proposal contract, policy
store) and 6d (gated executor spec) not started and wait for the owner's review.

## 6a: outcome labels (`sa/outcomes.py`)

Every card and every future proposal ends in one of `acted_on`, `ignored`, `undone`, `rejected`
(`pending` while it cannot yet be known), linked to the event that proves it. Labels are pure
functions of recorded events, so a replay reports what live would.

**Cards** (`label_card`), from `card_interactions` with the semantics the API documents: `tapped`
(engagement) and `acked` ("got it", mild positive) are `acted_on`; `dismissed` (swipe-away, "seen, no
comment") and `expired` are `ignored`; `not_useful` is `rejected`; a negative always wins, so a
demotion is never missed; no outcome past 24 hours is `ignored`.

**Device proposals** (`label_action`), per action type (`ACTION_TYPES`: `switch_on`, `switch_off`,
60-minute window, 30-minute undo; any other type is one more registration): `acted_on` is the
predicted state change appearing in the state history **whoever caused it** (a wall switch counts,
the cause is recorded as `household` or `alfr3d`); `rejected` is an explicit decline; `undone` only
exists for an action Alfr3d performed that a person reversed inside the undo window; `ignored` is
the window passing with nothing. Specified and tested on synthetic history: **there are no proposals
yet, so no device outcome has been measured**; the real ones start with the first proposals at
level 0.

**Where labels live.** No new table: card labels are derived from `card_interactions` (the impression
id already links an impression to its outcome); proposal outcomes will be recorded in
`sa_inferences.evidence` by 6c. A table is not clearly needed.

**Replay, last 8 weeks, real lake** (`python -m sa.outcomes --days 56`, read-only; 2026-09-24 to
2026-11-18): 95 impressions across 12 rules. **acted_on 4, rejected 1, ignored 90, undone 0, pending
0.** Per rule: `household_composition` 26 (2 acted on, 24 ignored), `time` 17 (1, 15, 1 rejected),
`rhythm_break_anomaly` 13 (1, 12), `email` 13, `weather` 8, `mood` 5, `now_playing` 5,
`attention_focus` 4, and one each for climate, cross-surface, household unusual day and travel.
Another 12 explicit outcomes (household_composition: 7 tapped, 1 dismissed; rhythm_break_anomaly: 3
dismissed; music: 1 dismissed) carry **no impression id** (older rows) and cannot be linked to an
impression: counted separately, never guessed. **Read with care:** "ignored" is mostly "no explicit
feedback within 24 hours", which a card the household saw and found fine also produces; it is a
weak label until feedback capture grows (the prompt's acted-on linkage re-check, about
2026-12-28, stands).

## 6b: predictor registry and one proof predictor (`sa/predictors.py`)

A predictor is declared once (`Predictor`: what it predicts, from which history, its floors) and uses
conditional frequency counts, a time-ordered held-out block, a probability, a confidence from the
shared layer-1 contract (`sa/confidence.py`, every term required, none defaulting to 1.0) and a
`because` list. Below its floors it says "insufficient evidence"; it also stays silent unless it
beats "always the usual rate" by `MIN_SKILL` (0.10) on the held-out block. A test caught this
needing a floor: pure noise scored +0.0003 and "passed" a bare "skill above zero". Weather,
calendar, indoor climate and location join later through the covariate engine and the discovery
screen, not as special cases. The module has no import that can reach a device (tested).

**Proof predictor `switch_usual_state`:** how likely is a switch or light ON (for at least half of
the local hour) at this hour on a weekday or weekend, learned from Home Assistant's state history
whoever changed the state. Smoothed cell, hour and overall frequencies; fitted on the first 70 % of
days, judged on the rest; floors of 10 training days and 72 held-out hours.

**Real lake, 6 HA switches** (`python -m sa.predictors`, read-only): **1 predictable, 1 too little
history, 4 with no skill.** `living_room_little_lamp_socket`: Brier 0.179 against 0.243 for the
usual rate, skill 0.26 (10 training days, 118 held-out hours). `living_room_polica_lights`: 3
training days, insufficient evidence. `computer_lamp_socket_1` (skill -0.01), `little_lamp_socket`
(-0.22) and `office_armoire_lights` (-0.21): no better than the usual rate. `teckin4_socket_1`: the
held-out baseline error is about zero because it was always off, so the skill figure (-17.6) is a
degenerate ratio, not a result. Small n by construction: five held-out days.

**An honest caveat about the one success.** That lamp's regularity (off about 04:30 and on about 22:00
UTC, on consecutive days) is the same rhythm the evidence inventory found among the switch changes
that had NO API command. State history cannot tell a household habit from a Home Assistant schedule,
and if it is an automation, predicting it adds nothing: the house already does it. So a predictable
switch is a candidate, not an opportunity; the open question for any proposal is whether something
already acts at that time.

## Not built, waiting for review

6c (proposal contract and autonomy policy schema, household scope first, every action type at level
0, no never-list, guests never grant) and 6d (the gated executor spec, and the replacement wording
for the "nothing actuates" rule, whose diff is shown first). No executor, no device command, no
promotion above level 0 anywhere in this phase.
