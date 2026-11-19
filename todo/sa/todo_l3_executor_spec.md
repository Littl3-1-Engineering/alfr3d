# Layer 3, item 4/4: the gated executor (Phase 6d) — SPEC ONLY

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 6d; design page
"Layer 3: anticipation with earned autonomy". Status 2026-11-19: **specification for the owner's
review. Nothing is implemented, and the prompt says the executor is not implemented until the owner
approves the 6c contract** (`todo_l3_proposal_policy_contract.md`, merged as a contract only) **and
this spec.** There is no executor, no route and no code path from a proposal to a device anywhere in
the repository.

## What it is

The one audited path from a proposal to an action. It exists to make doing something harder to do
by accident than not doing it. It reuses what the platform already has; it adds no second way to
touch a device.

## The path an action must take (every step must pass, in this order)

1. **Kill switch.** Read at **execution time**, not only when the proposal was made: `config`
   (name `autonomy_kill`). If set, stop; the result is level 0 (a card).
2. **Policy level.** `Policy.level(action_type, scope, context)` (default 0). Level 0: stop, show the
   card. Level 1: stop and ask; the household's one-tap confirm re-enters here as an explicit user
   command, not as autonomy. Levels 2 and 3 continue.
3. **Proposal valid.** `validate_proposal` (reasons, cost, reversibility, a registered action type);
   not expired.
4. **Guest check.** An action is never triggered from a guest's pattern.
5. **State re-check.** Read the entity's CURRENT state immediately before acting. If it already
   equals the target (someone just turned it on), do nothing and label the proposal `acted_on` by the
   household. Never issue a command that has no effect.
6. **Rate limit.** At most N executions per action type per hour (placeholder 3) and one per entity per
   10 minutes, so a bad prediction cannot loop. Over the limit: skip, log, and count it as a reason to
   review the type.
   **6b. Quiet hours.** Levels 2 and 3 never act inside the household quiet window (placeholder
   23:00 to 07:00 local), whatever the policy says: they fall back to a card. Level 1 is unaffected,
   since a person confirms it.
7. **Idempotency.** One execution per proposal id; a retry of the same id is refused.
8. **Execute through the existing path:** `service_daemon/utils/util_routines.control_iot_device(
   device_id, action_type, params, command_attribution={...})`, the routine engine's device control,
   which already records the command in `device_command_history`. The attribution carries
   `origin = "autonomy"` (a new value for the existing `origin` column; today `user` and `system`),
   the proposal id, the level, and the `because` list in `context`. One retry at most on a transient
   failure; a failed command is logged and is not an outcome.
9. **Audit, before and after.** An `autonomy` row in `household_events` (verb `acted`, with the
   `because`) before the command and the result after, so a crash between them is visible. Every
   blocked attempt is logged with the step that stopped it.
10. **Tell.** Level 3: tell immediately with an undo control ("Turned on the living-room lamp because
    it is usually on at this hour. Undo."). Level 2: standing permission, told in the day's summary
    with the same undo. (**Open question below.**)

## Undo

Where the device allows: the inverse command (`turn_on` and `turn_off`; brightness back to the prior
value, recorded at step 5). The undo window is per action type (`ActionType.undo_minutes`). A person
reversing it inside the window labels the action **undone** (`sa/outcomes.py`) and demotes the type
one level. **A failed or ambiguous undo** (the device did not change, or state history cannot show
which change was whose) **demotes straight to level 0** and raises a card.

## Kill switch and reset

`POST /api/autonomy/kill` (owner) returns every action type to level 0 at once and takes effect at
step 1 of the next attempt; `POST /api/autonomy/kill/reset` (owner) lifts it and promotes nothing.
Teach me shows the ladder per action type with a **one-tap reset to level 0**. All of it is written
to `sa_autonomy_log` (migration 0065, written, not run).

## Ships dark

The executor ships behind a feature flag that is **off**, and every action type is at level 0 by
default, so shipping it changes nothing. Turning it on without a promotion still changes nothing,
because a level 0 type never passes step 2. Nothing is promoted by the system.

## Tests that must exist before any code

Level 0 never reaches step 8 (the contract's acceptance test, extended end to end); the kill switch is
honoured at execution time even for a proposal made before it was set; a guest's pattern never
executes; a stale state is never commanded; every blocked attempt and every execution is audited
before and after; an undo inside the window demotes and one outside does not; a failed undo goes to
0; a proposal id never executes twice; the rate limits hold; the executor flag off means no command
under any policy.

## Decisions (owner, 2026-11-19)

1. **Levels 2 and 3** read as proposed: 2 acts without asking and is told in the day's summary; 3
   acts, is told at once, with a prominent undo. Agreed.
2. **Rate limits** (3 per action type per hour, 1 per entity per 10 minutes): agreed as placeholders,
   to be set against real execution data once anything runs.
3. **Quiet hours:** levels 2 and 3 never act in the quiet window (placeholder 23:00 to 07:00), whatever
   the policy says. Agreed; it is step 6b above.
4. **Order of approval:** contract (6c, merged as a contract only), this spec, then the executor flag.
   The executor is still not implemented.

## The "nothing actuates" rewording (NOT applied to anything the owner has not seen)

Owner-approved text (2026-11-18): "Alfr3d acts on the household's behalf only through the autonomy
ladder. Every action type starts at level 0 (predict only). An action type moves up only when the
owner promotes it, shown the evidence. Every action is explained, logged and undoable where the device
allows; an undo or a "not useful" demotes it; a kill switch returns everything to level 0.
Observation, never concern."

Where it replaces old wording, in this repository (tracked docs only): `todo_transition_learning.md`
(Out of scope), `todo_attention_telemetry.md`, `todo_esphome_situational_awareness.md`,
`todo_device_location_reporting.md`, and `SA_ROADMAP.md` (Principles). **Owner decision 2026-11-19:
`AGENTS.md` and `CLAUDE.md` stay gitignored and are not edited, committed or merged; the rule is not
added to either.** The Claude Code working rule "Nothing autonomously actuates a device" is in the
Notion prompt page, not in the repo; it is changed only with the owner's wording approval.
