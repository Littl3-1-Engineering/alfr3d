# SA: Earned interruption (DESIGN ONLY)

> **Layer:** L1 learner + consumer (card timing) · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) Step 4 "Card-feedback learner" · **Notion:** Alfr3d Timeline row "Earned interruption" (Planned) · **Related:** [todo_card_feedback_loop.md](todo_card_feedback_loop.md), [todo_l3_outcomes_predictors.md](todo_l3_outcomes_predictors.md) (outcome labels), "Day-shape briefing" (depends on this)
> **Prompt:** "card feedback, close SA gaps, start the next steps" (2026-11-14), Phase 4: write the design for a Beta-Binomial learner per (rule, daypart) plus a visible-time scalar; build it only when a few hundred impressions with interactions exist; until then report the count weekly in the roadmap and stop.

## Status: design written 2026-11-20. Nothing built, by design: the evidence is far too thin (below).

## The count today (read-only, production, 2026-11-20)

| | value |
|---|---|
| impressions (`action = 'impression'`, 2026-11-02 to 11-20) | **124** (deck 89, web 35), about 6.5 a day |
| explicit interactions since 2026-11-01 | **6**: `acked` 4, `dismissed` 1, `not_useful` 1 (all Deck) |
| rules with at least 5 explicit interactions | **0** (the most is `time` and `household_composition` with 3 and 2) |
| most impressions for one rule | `household_composition` 29, `time` 27, `rhythm_break_anomaly` 21, `email` 16, the other 8 rules 8 or fewer |
| `visible_ms` | present on every impression; 3 s to 6,657 s, rule means 20 s to 1,139 s |

At the current pace (about 0.3 explicit interactions a day) the trigger below is **early February 2027**,
low confidence: feedback only started with the 2026-11-15 Deck build.

Weekly count (read-only; run in `sa-awareness`, the roadmap line is updated from it):
```sql
SELECT SUM(action = 'impression') AS impressions,
       SUM(action IN ('tapped','acked','not_useful')) AS explicit,
       SUM(action = 'not_useful') AS not_useful
FROM card_interactions WHERE occurred_at >= '2026-11-01' AND action <> 'shown';
```

## Build trigger (proposed; the owner can change it)

Build the learner when **all** hold: at least **300 impressions** with an id and `visible_ms`; at least
**30 explicit interactions** (`tapped`, `acked`, `not_useful`); at least **two rules with 5 or more**
explicit each. Until then: report the three counts weekly in the roadmap and stop. Nothing below is
built before the trigger, except the weekly count.

## What it decides, and what it does not

- **Decides:** for a card rule in a daypart, whether to show it and in what order. A learned timing
  model, separate from the card's wording, which stays with the rule.
- **Does not decide:** what a card says; text-to-speech timing (speech has no outcome capture at all,
  so a speech learner would have nothing to learn from: a follow-up with its own capture first); anything
  about devices or actions (that is layer 3). No new card, `MAX_DISPLAYS == 26` unchanged.
- **Never touches** `urgent` cards or anything with the never-suppress override. Those are outside the
  model, whatever it learns.

## Why a Beta-Binomial and not a bandit

The roadmap row says "contextual bandit"; the prompt says Beta-Binomial. This design uses the posterior
and **no exploration**. A bandit has to deliberately show cards it believes are unwanted in order to
learn. Here every card is shown anyway today (the existing cooldown is soft), so there is a natural,
unbiased impression stream, and a learner that only ever *holds back* on strong evidence needs no
exploration. It stays simple, explainable and inspectable. Revisit only if a rule is held back so often
that it stops producing evidence (see "the absorbing-state trap").

## Outcome model (reuses `sa/outcomes.py`, no new labels)

"Ignored" is the default for a passive card, and 90 of 95 recent outcomes were ignored: it carries almost
no information. So the model keeps two rates apart and never treats "ignored" as a failure.

- **R, rejection:** P(`not_useful` | impression). The **only** evidence that can hold a card back.
- **E, engagement:** P(`tapped` or `acked` | impression). Evidence for ordering a card up, never for
  holding it back: an informational card (time, weather) is read, not tapped.

Per (rule, daypart) cell, each as a Beta posterior with a hierarchical prior so a thin cell borrows from
its rule, and a thin rule from all rules (partial pooling; the prior strength is a constant fixed by the
replay, not by hand). Swipe-away (`dismissed`) is neutral, as everywhere else. Dayparts are the **four
coarse buckets** `common/timeofday` already gives (morning, day, evening, night) at the household's local
hour, not DayContext's seven parts: at this n, seven is noise. (Impressions today fall mostly in local
evening and night, so most morning and day cells are empty.)

## The visible-time scalar (shadow only until it earns more)

`visible_ms` per (rule, daypart), on the log scale with a robust centre and spread (the scalar learner's
median and MAD sigma), capped at 30 minutes. Two honest caveats:

- Dwell mostly measures **how long the card stayed in the payload**, not how long anyone looked. The Deck
  tracker counts only interactive screen time, but a Deck on a counter is "interactive" for hours (the
  6,000 s impressions). So dwell is read only **relative to the rule's own history**.
- It can **never hold a card back on its own.** It adds a small, bounded adjustment to the ordering score
  and is reported in Teach-me. Whether it adds anything is measured in the replay; if it does not, it
  ships off.

## Decision rule (constants set by replay, not here)

1. **Order:** a card's rank within the display budget moves by at most one place from E (up) and from R
   (down), and only when the posterior interval excludes the rule's own pooled rate.
2. **Hold back in a daypart:** only when R's posterior says the rate is above a floor with high
   probability **and** the cell has a minimum number of impressions and at least 3 `not_useful`. The
   hold-back is **time-limited** and **reversible**; it shows in Teach-me with its evidence and a one-tap
   reset.
3. **The absorbing-state trap:** a card held back produces no impressions, so its posterior never
   updates and the silence would be permanent. Every hold-back therefore **expires after 28 days** and the
   card then runs a **7-day probation** under the normal rules; the evidence from the probation decides
   whether it returns. The owner can reset any rule at any time.
4. **Never silence a rule entirely:** a hold-back applies to one daypart; the rule keeps its other
   dayparts, and a security-relevant rule keeps all of them.

The existing suppression stays the reflex: dismissed or acked (60 min) and `not_useful` (24 h) cooldowns
per card identity are unchanged. The learner is the slow memory on top of it, applied at the same point
(`decide_displays`, via `_card_suppression_reason`, with a distinct reason `learned_daypart` that the
shadow review can count).

## Where it lives

A new nightly learner `card_timing` in `sa-learner`: profiles in `sa_profiles` (`subject_type = 'rule'`,
`subject_id = rule_id`, signal `card.timing`; params per daypart: the Beta parameters for R and E, n, the
dwell centre and spread). **No new table and no migration**: the profile contract already exists.
`sa-awareness` reloads it like every profile. Confidence follows the contract (`sufficiency x coverage x
source_quality x stability`); `source_quality` is deliberately low (explicit feedback is sparse and comes
from one person's device). Read-only API: it appears in the Teach-me route (profile, confidence,
evidence) with no new endpoint.

## Known confounds, stated up front

- **One household, effectively one voice:** the explicit feedback so far is all from the Deck. Per-person
  scope is possible (`user_id` is recorded) and is **not built**, matching the household-scope-first rule.
- **Two surfaces:** the same card on the web and the Deck at once is two impressions. Counted separately;
  the replay reports the double count's effect.
- **Unlinked Brief dismissals:** `BriefRepository.dismiss` reports `dismissed` with no `impression_id`, so
  those swipes cannot be tied to a display. A small Deck fix, listed as a prerequisite below.
- **A known mislabel:** the Deck's "ALFR3D's music pick" rule matches any `mode == "music"` card (including
  plain `now_playing`), so feedback on it lands on the wrong rule (noted in `todo_card_feedback_loop.md`).
  Fix before trusting the music cells.
- **Selection:** a tap or a not-useful needs a person at the screen; unattended displays only add ignores.

## Phases (after the trigger; each ends with a gate)

- **L0 (now): the weekly count.** Report the three counts in the roadmap each week. Nothing else.
- **L1: fit in shadow.** The learner writes profiles; a replay report (the existing `sa.replay` format)
  compares predicted R against held-out outcomes, time-blocked, and states "would have held back N
  cards in cell X". No effect on any card. *Gate:* held-out calibration the owner accepts, or stop.
- **L2: ordering only.** Apply the order rule, behind a flag. *Gate:* no change to card counts; the
  replay's predicted rank changes match the live ones (parity).
- **L3: hold-back.** Only after L2 has run for weeks and the owner approves, with the 28-day expiry and
  probation, and the Teach-me reset in place.

## Acceptance (for the whole item)

A replay-backed shadow report exists before any effect; no card is ever held back on dwell alone; urgent
and never-suppress cards are untouched (a test); every hold-back expires; the learned state shows in
Teach-me and resets; card counts and `MAX_DISPLAYS` are unchanged; CI green.

## Prerequisites to do earlier (small, independent)

1. Deck: tie Brief dismissals to an `impression_id` (cross-repo, `alfr3d_deck`).
2. Deck: stop the "music pick" rule claiming plain `now_playing` cards.

## Decisions needed from the owner

1. Scope: cards only (this design), or also speech timing (needs a speech-outcome capture first)?
2. Are the trigger numbers (300 impressions, 30 explicit, two rules with 5) right?
3. Four dayparts, or DayContext's seven?
4. May the learner ever hold a card back (L3), or only reorder (L2)?
5. Do the two small Deck prerequisites go ahead now?

## Out of scope

Speech timing; wording or content; per-person models; any new card; any device action; population
statistics or anything cross-household; a bandit with exploration.
