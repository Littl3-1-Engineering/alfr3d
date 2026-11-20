# Layer 3: proposals, shadow first (step 2 of the executor-review order)

Status 2026-11-20: **the shadow replay is built** (`sa/proposal_shadow.py`, read-only, nothing shown,
stored or commanded). The visible level-0 proposal card is **not built**, for the reason below, and
waits for the owner. Follows `todo_l3_executor_spec.md` (review and order of work).

## Why shadow first

The planned step was "proposal cards at level 0, so real outcomes start to exist". Two things
changed the order:

- **A new card is not a backend-only change.** The Deck (`SituationalInsights.kt`, one parser per
  mode) and the web frontend (`SituationalAwareness.jsx`, an icon per mode) each render cards by
  `mode`. A `switch_habit` card needs Kotlin and JSX, a Deck release to Play, and `MAX_DISPLAYS` and
  the engine safety net move from 26 to 27. That is not an overnight, no-owner change.
- **The evidence about whether proposals are worth showing exists already.** The state history says
  what the household did after every hour the predictor would have spoken. Replaying that costs no
  card and no risk, and answers "would a proposal have been right, and better than chance?" first.

## What the replay does

For each switch and each of the last N days (default 14): fit the predictor on the days BEFORE that
day only; at the start of each hour, if it is off and the predictor is at least 85 % sure it is
usually on (or on and at most 10 % sure), with confidence at least 0.3, a would-be `switch_on` (or
`switch_off`) proposal exists (no repeat inside 3 hours). It is labelled by `outcomes.label_action`
against the next 60 minutes of real state history (whoever changed it), the counts go through
`outcomes.evidence_from_labels`, and `proposals.recommend` says what a promotion screen would show.
Autonomous commands are excluded from training. The report puts each switch's **base rate** (how often
the change happens in that hour anyway) beside the acted-on share, because a lamp turns on within the
hour often without any help.

Run it: `python -m sa.proposal_shadow --lake /lake --days 14` (read-only; on the NUC with the same
temp-copy technique as the parity runs until it is deployed).

## First real result (production lake, 2026-11-20, 14 days)

**Zero proposals.** Across the six switches the predictor was willing to speak on 1 evaluation day in
total, for one switch (`switch.living_room_little_lamp_socket`), and made no proposal that day. The
other five never spoke: too little history, or no skill over the usual rate. The recommendation is
the contract's own: "only 0 proposals (need 20)". This agrees with the earlier measurement (one of
six switches shows a pattern) and says the same thing more strongly: **a proposal card would have
shown nothing in the last two weeks, so there is nothing to learn from yet by showing one.**

## What changes the answer, and what to do next

- More history (a few more weeks) and more regular switches. Re-run the replay weekly; it is cheap.
- A lower HIGH/LOW bar would produce proposals, but that is tuning to get an answer; the bars stay
  as placeholders until there is evidence to set them against.
- If, after several weeks, the replay shows proposals acted on well above their base rate, the
  visible level-0 card becomes worth the Deck and web work, and this doc's plan resumes there.
- Until then Layer 3 has nothing to propose, so the executor has nothing to do. That is the
  honest state, not a gap to fill.

## Tests

`tests/test_sa_proposal_shadow.py`: a regular lamp gets proposals the household acts on, in the hour
before it comes on; the base rate is reported; an irregular lamp, too little history and a lamp the
executor runs all get none; a day is judged only from the days before it (a day the routine breaks
is labelled ignored); a proposal whose outcome is not yet knowable is not counted; and the module
cannot reach a device or a network.
