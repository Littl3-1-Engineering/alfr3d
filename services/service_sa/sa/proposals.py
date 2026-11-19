"""Proposal contract and autonomy policy (Layer 3 3/4, Phase 6c;
todo/sa/todo_l3_proposal_policy_contract.md). A CONTRACT, not an executor.

Layer 3 may propose an action and, only where the owner has granted it, perform it. This module
defines the two things that decide that, as pure data and pure functions:

- a **Proposal**: the action, the reason (a `because` list), probability and confidence (the layer-1
  contract), the **cost of being wrong** and the **reversibility**, so the owner's promotion screen
  can show them beside the evidence;
- the **autonomy policy**: a level per (action type, scope, context), every one defaulting to 0,
  with its evidence, who granted it and when.

The ladder: 0 predict only (at most a card), 1 suggest with one-tap confirm, 2 standing permission,
3 act then tell, with undo. Rules enforced here:

- **Default 0.** A row that does not exist is level 0; so is every action type nobody registered.
- **Promotion is always an owner decision, shown with its evidence** (`promote` needs the owner role
  and the evidence snapshot the owner saw). The system may recommend (`recommend`); it never
  promotes.
  **Guests never grant, promote, or have an action triggered from their own pattern.**
- **Demotion is automatic and immediate** after an undo or a "not useful" (one level down), after a
  failed or ambiguous undo (straight to 0), and on the kill switch (everything to 0).
- **No never-list**: any action type can be proposed and can earn approval, so what limits it is
  information and friction: every proposal carries its cost and reversibility.
- **Scope**: household scope only is built. Person and presence-conditioned scopes are named in the
  schema so they can be added later, but `validate_row` refuses them until the owner asks.

**Nothing here executes anything.** `decide` returns what SHOULD happen at a level (`card`, `ask`,
`standing`, `act_then_tell`); levels 2 and 3 name an executor that does not exist in this phase. The
module imports nothing that can reach a device (a test checks its source), and at level 0 `decide`
can only ever return a card.
"""

from dataclasses import dataclass, field
from datetime import datetime

PREDICT_ONLY, SUGGEST, STANDING, ACT_THEN_TELL = 0, 1, 2, 3
LEVELS = (PREDICT_ONLY, SUGGEST, STANDING, ACT_THEN_TELL)
LEVEL_NAMES = {0: "predict only", 1: "suggest", 2: "standing permission", 3: "act then tell"}
MODE_BY_LEVEL = {0: "card", 1: "ask", 2: "standing", 3: "act_then_tell"}

# Scopes: household is built; the others are designed for and refused until the owner asks.
HOUSEHOLD, PERSON, PRESENCE = "household", "person", "presence"
SCOPES = (HOUSEHOLD, PERSON, PRESENCE)
BUILT_SCOPES = (HOUSEHOLD,)

OWNER, RESIDENT, GUEST = "owner", "resident", "guest"
PROMOTERS = (OWNER,)  # the technoking backdoor is Athos-only and is not a role to design around

# What the cost of being wrong and the reversibility look like on the promotion screen.
COSTS = ("trivial", "minor", "moderate", "serious")
REVERSIBILITY = ("undoable", "manual", "irreversible")
DEFAULT_CONTEXT = "*"  # "any context"; a context is a key the policy was granted for


@dataclass
class Proposal:
    action_type: str  # a registered type (sa/outcomes.py ACTION_TYPES), e.g. one for a switch
    subject: str  # what it acts on (an entity), never a person's wellbeing
    target_state: str
    because: list  # the reasons, as the layer-1 contract does
    probability: float
    confidence: float
    cost_of_being_wrong: str
    reversibility: str
    predictor: str = ""
    context: str = DEFAULT_CONTEXT
    triggered_by: dict = field(default_factory=dict)  # {"person_id", "role"} of the pattern owner
    created_at: datetime = None
    expires_at: datetime = None


def validate_proposal(proposal, known_action_types):
    """Problems with a proposal, as strings (empty when it is well formed). A proposal without its
    reasons, its cost or its reversibility is malformed: the owner could not judge it."""
    problems = []
    if proposal.action_type not in known_action_types:
        problems.append(f"unknown action type {proposal.action_type!r}")
    if not proposal.because:
        problems.append("a proposal must say why (because)")
    for name in ("probability", "confidence"):
        value = getattr(proposal, name)
        if value is None or not 0.0 <= value <= 1.0:
            problems.append(f"{name} must be in [0, 1]")
    if proposal.cost_of_being_wrong not in COSTS:
        problems.append(f"cost_of_being_wrong must be one of {COSTS}")
    if proposal.reversibility not in REVERSIBILITY:
        problems.append(f"reversibility must be one of {REVERSIBILITY}")
    if not proposal.subject or not proposal.target_state:
        problems.append("a proposal needs a subject and a target state")
    return problems


@dataclass
class PolicyRow:
    action_type: str
    scope: str = HOUSEHOLD
    scope_key: str = ""  # a person id for person scope, a condition key for presence scope
    context: str = DEFAULT_CONTEXT
    level: int = PREDICT_ONLY
    evidence: dict = field(default_factory=dict)  # counts shown at promotion
    granted_by: str = None
    granted_at: datetime = None

    @property
    def key(self):
        return (self.action_type, self.scope, self.scope_key, self.context)


def validate_row(row):
    problems = []
    if row.level not in LEVELS:
        problems.append(f"level must be one of {LEVELS}")
    if row.scope not in SCOPES:
        problems.append(f"unknown scope {row.scope!r}")
    elif row.scope not in BUILT_SCOPES:
        problems.append(f"{row.scope} scope is designed for but not built; the owner has not asked")
    if row.level > PREDICT_ONLY and not (row.granted_by and row.granted_at and row.evidence):
        problems.append("a level above 0 needs who granted it, when, and the evidence shown")
    return problems


class Policy:
    """The autonomy policy: levels per (action type, scope, context), default 0, with a change log.
    In memory here; the table design is in todo_l3_proposal_policy_contract.md. `killed` returns
    every level to 0 until the owner resets it."""

    def __init__(self, rows=()):
        self.rows = {r.key: r for r in rows}
        self.log = []  # append-only: every change, who, why, with the evidence
        self.killed = False

    def level(self, action_type, scope=HOUSEHOLD, scope_key="", context=DEFAULT_CONTEXT):
        """The level in force: 0 for a missing row, a context not granted, or when killed. A grant
        for one context does not leak into another."""
        if self.killed:
            return PREDICT_ONLY
        row = self.rows.get((action_type, scope, scope_key, context))
        return row.level if row else PREDICT_ONLY

    def _record(self, row, before, after, actor, reason, evidence, now):
        self.log.append(
            {
                "key": row.key,
                "from": before,
                "to": after,
                "actor": actor,
                "reason": reason,
                "evidence": evidence,
                "at": now,
            }
        )

    def promote(self, row_key, to_level, actor_id, actor_role, evidence, now):
        """Raise a level. Only the owner, only one step at a time, only with the evidence snapshot
        the owner was shown. Guests (and everyone but the owner) are refused."""
        if actor_role not in PROMOTERS:
            raise PermissionError(f"only the owner promotes an action type, not {actor_role!r}")
        if not evidence:
            raise ValueError("promotion needs the evidence the owner was shown")
        action_type, scope, scope_key, context = row_key
        row = self.rows.get(row_key) or PolicyRow(action_type, scope, scope_key, context)
        if to_level != row.level + 1 or to_level not in LEVELS:
            raise ValueError("promote one level at a time, up to level 3")
        candidate = PolicyRow(
            action_type, scope, scope_key, context, to_level, evidence, actor_id, now
        )
        problems = validate_row(candidate)
        if problems:
            raise ValueError("; ".join(problems))
        before, self.rows[row_key] = row.level, candidate
        self._record(candidate, before, to_level, actor_id, "owner promotion", evidence, now)
        return candidate

    def demote(self, row_key, reason, now, failed_undo=False):
        """Automatic and immediate: one level down after an undo or a "not useful", straight to 0
        after a failed or ambiguous undo. Nobody's approval is needed to be safer."""
        row = self.rows.get(row_key)
        if row is None or row.level == PREDICT_ONLY:
            return row
        to = PREDICT_ONLY if failed_undo else row.level - 1
        before, row.level = row.level, to
        self._record(row, before, to, "system", reason, row.evidence, now)
        return row

    def kill(self, actor_id, now):
        """The global kill switch: every action type returns to level 0 at once."""
        self.killed = True
        self.log.append(
            {"key": "*", "from": "any", "to": 0, "actor": actor_id, "reason": "kill switch",
             "evidence": {}, "at": now}
        )  # fmt: skip

    def reset(self, actor_id, actor_role, now):
        """Owner-only: lift the kill switch. Levels come back as they were; nothing is promoted."""
        if actor_role not in PROMOTERS:
            raise PermissionError("only the owner resets the kill switch")
        self.killed = False
        self.log.append(
            {"key": "*", "from": 0, "to": "restored", "actor": actor_id,
             "reason": "kill switch reset", "evidence": {}, "at": now}
        )  # fmt: skip


def recommend(evidence, min_proposals=20, min_acceptance=0.8, max_undo_rate=0.05):
    """Whether the evidence would SUPPORT asking the owner for a promotion: a recommendation shown
    to the owner, never a promotion. `evidence`: {"proposals", "acted_on", "undone", "rejected"}."""
    n = evidence.get("proposals", 0)
    if n < min_proposals:
        return {"recommend": False, "reason": f"only {n} proposals (need {min_proposals})"}
    acceptance = evidence.get("acted_on", 0) / n
    undo = evidence.get("undone", 0) / n
    if acceptance < min_acceptance:
        return {
            "recommend": False,
            "reason": f"acceptance {acceptance:.0%} under {min_acceptance:.0%}",
        }
    if undo > max_undo_rate:
        return {"recommend": False, "reason": f"undo rate {undo:.0%} over {max_undo_rate:.0%}"}
    return {
        "recommend": True,
        "reason": f"{n} proposals, {acceptance:.0%} accepted, {undo:.0%} undone",
    }


def decide(proposal, policy, known_action_types):
    """What should happen to this proposal, as data: {"mode", "level", "blocked", "why"}. It NEVER
    executes anything. `mode` is `card` at level 0, `ask` at 1, and `standing` or `act_then_tell` at
    2 and 3 (which name an executor this phase does not have). A malformed proposal, a guest's
    pattern, or a killed policy is blocked."""
    problems = validate_proposal(proposal, known_action_types)
    if problems:
        return {"mode": None, "level": None, "blocked": True, "why": "; ".join(problems)}
    if (proposal.triggered_by or {}).get("role") == GUEST:
        return {
            "mode": None,
            "level": None,
            "blocked": True,
            "why": "a guest's pattern never triggers an action",
        }
    level = policy.level(proposal.action_type, context=proposal.context)
    if level == PREDICT_ONLY:
        # at most a card: the only mode reachable without an owner grant
        return {"mode": "card", "level": 0, "blocked": False, "why": "level 0: predict only"}
    return {
        "mode": MODE_BY_LEVEL[level],
        "level": level,
        "blocked": False,
        "why": f"level {level} ({LEVEL_NAMES[level]}) granted for this context",
    }


def starting_rows(action_types):
    """Level-0 policy rows for registered action types: the starting policy is DATA over the
    registry (the first two types are lights and switches), never hard-coded here."""
    return [PolicyRow(action_type) for action_type in action_types]
