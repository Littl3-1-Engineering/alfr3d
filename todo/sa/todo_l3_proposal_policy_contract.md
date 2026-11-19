# Layer 3, item 3/4: proposal contract and autonomy policy (Phase 6c)

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 6c; design page
"Layer 3: anticipation with earned autonomy". Status 2026-11-19: **contract written and tested, for
the owner's review.** It is the schema and the API contract only: **no migration is written or run,
no route is built, no executor exists, and nothing can execute a device command.** The code is
`sa/proposals.py` (pure data and pure functions) and `tests/test_sa_proposals.py`.

## The ladder and the rules it enforces

0 predict only (at most a card), 1 suggest with one-tap confirm, 2 standing permission the owner
grants, 3 act then tell, with undo. Per **action type, scope and context.**

- **Default 0**: a row that does not exist, an unregistered action type, and a context that was not
  granted are all level 0. A grant for the evening does not leak into the morning.
- **Promotion is always an owner decision, shown with its evidence**: only the `owner` role, one
  level at a time, with the evidence snapshot the owner was shown. The system may `recommend` (a
  proposal to ask the owner, with its reason) and never promotes. **Guests never grant, promote, or
  have an action triggered from their own pattern.** The technoking backdoor is not a role to design
  around.
- **Demotion is automatic and immediate**: one level down after an undo or a "not useful"; straight
  to 0 after a failed or ambiguous undo. A **kill switch** returns every action type to 0 at once;
  only the owner lifts it, and lifting it promotes nothing.
- **No never-list** (owner decision 2026-11-18): any registered action type can be proposed and can
  earn a level. What limits it is information and friction: every proposal carries its **cost of
  being wrong** (`trivial`, `minor`, `moderate`, `serious`) and its **reversibility** (`undoable`,
  `manual`, `irreversible`), and the promotion screen shows them beside the evidence.
- **Scope**: household first (a grant applies whoever is home; an undo by any resident demotes it for
  the household; only the owner re-promotes). `person` and `presence` (household conditioned on who
  is home) are in the schema so they can be added later, and the code **refuses them** until the
  owner asks.
- **First action types: lights and switches** (`switch_on`, `switch_off` in `sa/outcomes.py`
  `ACTION_TYPES`), as **level-0 starting rows over that registry** (`starting_rows`), not code in the
  contract: any other type is one more registration.

## Proposal (the contract)

| field | meaning |
|---|---|
| `action_type` | a registered type (the registry `sa/outcomes.ACTION_TYPES`) |
| `subject`, `target_state` | what it would act on and the state it would set; never a person's wellbeing |
| `because` | the reasons, required: a proposal that cannot say why is malformed |
| `probability`, `confidence` | the layer-1 contract, both in [0, 1] |
| `cost_of_being_wrong`, `reversibility` | required, from the fixed vocabularies above |
| `predictor`, `context` | where it came from and the context it applies to |
| `triggered_by` | `{person_id, role}` of the pattern's owner (a guest's blocks it) |
| `created_at`, `expires_at` | when it was made and when it lapses (the window in `ACTION_TYPES`) |

`decide(proposal, policy)` returns **data, never an action**: `{mode, level, blocked, why}` with `mode`
`card` at level 0, `ask` at 1, and `standing` / `act_then_tell` at 2 and 3 (which name an executor this
phase does not have). A malformed proposal, an unregistered type, a guest's pattern or a killed
policy is `blocked`.

**Acceptance test (the prompt's):** nothing at level 0 can execute a device command. It holds for
two reasons the tests pin: the module has no import or symbol that can reach a device or a network
(`device_control`, `control_iot_device`, the Kafka producer, `requests`, the database, a subprocess,
or any `execute*` function), and at level 0 `decide` returns only `card` for every combination of
cost and reversibility.

## Table design (NOT a migration, nothing created)

`sa_autonomy_policy`: one row per grant. Primary key `(action_type, scope, scope_key, context)`.

```sql
CREATE TABLE sa_autonomy_policy (
  action_type VARCHAR(64) NOT NULL,
  scope       ENUM('household','person','presence') NOT NULL DEFAULT 'household',
  scope_key   VARCHAR(64) NOT NULL DEFAULT '',   -- a person id, or a presence-condition key
  context     VARCHAR(64) NOT NULL DEFAULT '*',
  level       TINYINT NOT NULL DEFAULT 0,        -- 0..3
  evidence    JSON NOT NULL,                     -- the counts the owner was shown
  granted_by  VARCHAR(64) NULL,
  granted_at  DATETIME NULL,
  updated_at  DATETIME NOT NULL,
  PRIMARY KEY (action_type, scope, scope_key, context)
);
CREATE TABLE sa_autonomy_log (                   -- append-only audit of every change
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  action_type VARCHAR(64) NOT NULL, scope VARCHAR(16) NOT NULL, scope_key VARCHAR(64) NOT NULL,
  context VARCHAR(64) NOT NULL, from_level VARCHAR(16) NOT NULL, to_level VARCHAR(16) NOT NULL,
  actor VARCHAR(64) NOT NULL,                    -- a user id, or 'system' for automatic demotion
  reason VARCHAR(255) NOT NULL, evidence JSON NOT NULL, at DATETIME NOT NULL,
  KEY (action_type, at)
);
```

A kill switch is one row in a small settings table (or a flag in `config`), not a column per row.
**Proposals are not a new table**: a proposal is a layer-3 inference in `sa_inferences` (kind
`proposal`), its `evidence` carrying the fields above and, later, its outcome label from
`sa/outcomes.py`. That reuses the contract and keeps one place for "what was predicted and how it
ended". The migration is written only after the owner approves this design, with the backup and plan
shown first.

## API contract (NOT built)

All under `/api/autonomy`, JSON, bearer-authenticated; `guest` is refused on every route.

- `GET /policy`: every row with level, scope, context, evidence, `granted_by`, `granted_at`, and the
  system's `recommend` result (a recommendation, never an action). Resident or above.
- `GET /proposals?status=&action_type=`: recent proposals with their `because`, cost, reversibility
  and outcome label. Resident or above.
- `POST /policy/promote` `{action_type, scope, context, to_level, evidence_digest}`: **owner only.**
  `evidence_digest` is a hash of the evidence the owner saw; the server recomputes the evidence and
  **rejects the request if it changed** (409), so a promotion is always of what was shown. One level
  at a time. Returns the new row.
- `POST /policy/demote` `{action_type, scope, context, reason}`: owner, or the system itself after an
  undo / not-useful / failed undo. Never needs approval to be safer.
- `POST /kill` and `POST /kill/reset`: owner only; kill needs no confirmation.
- Teach me shows the ladder with a one-tap reset to level 0 per type, using these routes. The UI waits
  for the owner's review.

## Decisions (owner, 2026-11-19)

1. **Demotion size: one level per undo or "not useful", straight to 0 on a failed or ambiguous undo,
   for now.** Direction to refine later: **quick to judge, slow to forgive.** Demotion is already
   immediate; the asymmetric half is not built and is proposed here for the owner to confirm:
   after a demotion, re-promotion needs (a) a cooling-off period (proposed 14 days), (b) a fresh
   evidence window that starts at the demotion, not the old counts, and (c) a second demotion inside
   the cooling-off doubles it. Numbers are placeholders until real outcomes exist.
2. **Promotion one level at a time**, never a jump. Agreed.
3. **Recommendation thresholds** (20 proposals, 80 % acted on, at most 5 % undone): agreed as
   placeholders, to be set against real outcome data.
4. **Proposals are layer-3 inferences in `sa_inferences`** (kind `proposal`), not a new table. Agreed.
5. **Table design approved.** Migration 0065 is written (`setup/migration_058_sa_autonomy_policy.sql` plus `0065_sa_autonomy_policy.py`, round-tripped on a throwaway MySQL 8: upgrade, downgrade to 0064, upgrade, both tables empty, a bare row defaults to household scope and level 0) and **run on production 2026-11-19** (backup `_pre_0065`, 40.5 MB, verified; `alembic_version` 0065; both tables empty); the verified backup and
   the plan are shown before anything touches production. The kill switch is one row in the existing
   `config` table (name `autonomy_kill`), not a new table.
6. The replacement wording for the "nothing actuates" rule is not applied anywhere; its diff comes
   with 6d (todo_l3_executor_spec.md).
