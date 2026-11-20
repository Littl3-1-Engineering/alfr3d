# Layer 3: re-promotion after a demotion ("quick to judge, slow to forgive")

**Status: BUILT (2026-11-20) in `sa/proposals.py` as pure data and functions, all four decisions approved as
recommended. No migration, no executor, nothing acts. Numbers are still placeholders.**
Follows decision 1 in `todo_l3_proposal_policy_contract.md`. Every number below is a placeholder:
there are no real proposals yet, so there are no outcomes to set them against.

## The problem

Demotion is immediate and needs nobody's approval (one level after an undo or a "not useful",
straight to 0 after a failed or ambiguous undo). Promotion is slow but only in the sense that the
owner must say yes and see evidence. Nothing yet stops this loop: an action type earns level 2, gets
undone, is demoted to 1, and the same old counts (24 proposals, 21 accepted) immediately recommend
promoting it again. The old evidence includes the very behaviour that just failed, so it should not
count for much, and a type that keeps failing should earn trust back more slowly each time.

## Rules

1. **Cooling-off.** After a demotion that the system made (undo, "not useful", failed undo), that
   key `(action_type, scope, scope_key, context)` cannot be promoted for `base` days. Placeholder:
   14 days.
2. **Fresh evidence.** `recommend()` counts only proposals and outcomes **since the last demotion**.
   The pre-demotion counts are still shown to the owner, labelled as before the demotion, but they
   do not satisfy the thresholds.
3. **It gets longer each time.** The cooling-off is `base * 2^(n-1)` days, where `n` is the number of
   system demotions of that key in the trailing 90 days, capped at 112 days (16 weeks). A demotion
   outside that window starts the count again, so a type that behaved for three months is forgiven.
4. **A failed or ambiguous undo counts as two.** It is the worst case (we could not take back what we
   did), so it starts at 28 days.
5. **Owner decisions do not start a cooling-off.** If the owner demotes a type by hand, or hits the
   kill switch, that was a choice they can reverse. Only automatic demotions are slow to forgive.
   Resetting the kill switch restores the levels as they were and promotes nothing.
6. **The owner can still decide.** A promotion inside the cooling-off is refused unless the owner
   passes an explicit override that names what they were shown (days remaining, the demotion that
   caused it). The override is logged with the evidence. There is no never-list, so the friction is
   information, not a wall. The system never overrides.
7. **Guests and residents** cannot promote or override. Unchanged.

## What it needs (no migration)

State is already in `sa_autonomy_log`: every demotion is a row with actor `system`, `from_level`,
`to_level`, a reason and a time. Cooling-off is a pure function of that log and `now`:

```python
def cooling_off(log, key, base_days=14, window_days=90, cap_days=112):
    """A CoolingOff(until, days, count, last_demoted_at); until is None when never demoted.
    `Policy.cooling_off(key)` wraps it; `CoolingOff.active(now)` says whether it applies."""
```

- `Policy.promote(...)` gains `override=None`. Inside the cooling-off it raises `ValueError`
  naming the date, unless the owner supplies `override={"ack_days_remaining": n, ...}`, which is
  recorded in the log entry's evidence.
- `recommend(evidence, cooling_until=None, now=None)` returns `recommend: False` with the reason
  `cooling off until 2026-12-04 (after an undo on 2026-11-20)` before it looks at counts, and counts
  only the post-demotion evidence passed in.
- `Policy.demote(..., actor="system")` writes the log row that carries the cooling-off. A failed undo
  has `weight` 2 in the row; a demotion with any other actor (the owner by hand) starts none.
- The window is anchored at the latest demotion, not at `now`, so the length cannot shrink as time
  passes.
- The API's `GET /policy` row gains `cooling_off_until`, `demotions_90d` and the fresh evidence
  window, so the owner sees them next to the recommendation. The API is not built yet; this is its
  contract.

## Tests that would pin it

- A demotion starts a cooling-off; a promotion inside it is refused for a resident, a guest and an
  owner without an override; allowed for the owner with one, and the override is in the log.
- The day after the cooling-off ends, promotion works again.
- Second system demotion inside 90 days doubles it (14, 28, 56, capped at 112); one outside the
  window starts again at 14.
- A failed undo starts at 28.
- An owner demotion and a kill switch start no cooling-off.
- `recommend` ignores pre-demotion counts and says why; a different context or action type is
  unaffected.
- A grant for one key never changes the cooling-off of another.
- Nothing in `proposals.py` gains an import that can reach a device (existing test).

## What this does not do

- It does not make anything act. The executor is still a spec and ships dark at level 0.
- It cannot be tested against real outcomes: none exist. Synthetic logs only, and the numbers stay
  placeholders until the first proposals have outcome labels.
- It does not cover person or presence scope (household scope only is built).

## Decisions (owner, 2026-11-20): all four approved as recommended

1. **Override or no override?** Recommended: the owner may override with an acknowledgement (rule 6).
   The alternative is a hard wall until the date, which contradicts "no never-list" but is simpler.
2. **Numbers:** 14 days, doubling, 90-day window, cap 112. Recommended as written for a placeholder.
3. **Failed undo counts double** (starts at 28 days). Recommended.
4. **Owner-initiated demotion and kill switch start no cooling-off** (rule 5). Recommended.
