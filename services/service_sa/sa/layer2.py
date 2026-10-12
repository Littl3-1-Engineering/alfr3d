"""Generic layer 2 (LF-6, todo/sa/todo_lf6_layer2.md): combine layer-1 inferences, weighted by
confidence, into statements no single learner can make.

Layer 2 reads layer-1 rows from sa_inferences and nothing else. A `Rule` says which rows belong
together (one subject: a person, the household) and how much to trust the group; this module does
the maths once:

1. every parent belongs to a source FAMILY (`family_of`). Parents in one family are not
   independent evidence (a phone's presence and its device rhythm are the same arp sightings), so
   a family votes once, by its most surprising parent;
2. families are combined with confidence-weighted Fisher, capped at the best family's p so a
   weakly trusted extra family can never make the result less surprising;
3. confidence is the mean of the voting families' confidence, optionally scaled by the rule's
   corroboration share (agreeing evidence from the same family makes a result more believable,
   not more surprising).

A new layer-2 inference is a new `Rule` subclass and one line in `shadow.RULES`; it does not touch
the combination code, the persistence or the runner.
"""

import math
from datetime import timedelta

from sa.learners.base import Inference

# A layer-1 deviation is re-upserted each awareness cycle (60 s) while it lasts. A row not
# refreshed in this long has ended and is not evidence.
FRESH_MINUTES = 5
DEFAULT_MIN_BITS = 3.0
SIGNAL_CALENDAR_BUSY = "calendar.busy"

# Where a layer-1 signal's evidence comes from. A learner can override per inference by putting
# evidence["family"]. Signals with no family are skipped, never silently counted as independent.
FAMILY_BY_SIGNAL = {
    "presence.home": "network",
    "device.online": "network",
    "device.session_minutes": "network",
    "presence.daytime": "network",
    SIGNAL_CALENDAR_BUSY: "calendar",
}
# Series and streams share one signal each; their key says where they came from.
FAMILY_BY_KEY_PREFIX = (
    ("esphome:", "climate"),
    ("ha:", "ha"),
    ("attention:", "attention"),
    ("email", "email"),
    ("event:", "events"),
)


def family_of(inference):
    """The source family of a layer-1 inference, or None if unknown."""
    evidence = inference.evidence or {}
    if evidence.get("family"):
        return evidence["family"]
    if inference.signal in FAMILY_BY_SIGNAL:
        return FAMILY_BY_SIGNAL[inference.signal]
    key = evidence.get("series") or evidence.get("stream") or ""
    for prefix, family in FAMILY_BY_KEY_PREFIX:
        if key.startswith(prefix):
            return family
    return None


def fisher_p(ps, weights):
    """P(chi-square_{2k} >= X) for X = -2 * sum(w * ln p). Closed form for even degrees of
    freedom: exp(-X/2) * sum_{j<k} (X/2)^j / j!."""
    k = len(ps)
    x = -2.0 * sum(w * math.log(max(p, 1e-300)) for p, w in zip(ps, weights))
    half = x / 2.0
    term, total = 1.0, 1.0
    for j in range(1, k):
        term *= half / j
        total += term
    return min(1.0, math.exp(-half) * total)


class Group:
    """The parents one rule gathered for one subject.

    anchor: the parent that makes this a candidate at all (e.g. the away presence deviation);
    parents: every parent including the anchor; share: corroboration in [0, 1] or None when there
    is nothing to corroborate with; evidence: rule-specific fields copied onto the result;
    explained_by: layer-1 rows that make the anchor less surprising (a booked event explains an
    absence). They never vote, since they carry no probability; they discount the surprise."""

    def __init__(
        self,
        subject_id,
        anchor,
        parents,
        share=None,
        evidence=None,
        explained_by=(),
        window_start=None,
    ):
        self.subject_id = str(subject_id)
        self.anchor = anchor
        self.parents = parents
        self.share = share
        self.evidence = evidence or {}
        self.explained_by = list(explained_by)
        self.window_start = window_start  # default: the anchor's; part of the upsert key


class Rule:
    """One layer-2 inference. Subclasses set the class fields and implement `groups`."""

    name = ""
    version = "1"
    signal = ""
    subject_type = "user"
    min_bits = DEFAULT_MIN_BITS
    corroboration_floor = 0.6  # confidence multiplier at zero corroboration
    explained_discount = 0.7  # share of the surprise (in bits) an explanation removes
    # Cap the combined p at the best family's, so more evidence never lowers surprise. A rule whose
    # threshold was calibrated on the plain weighted Fisher p (household day) turns this off.
    cap_at_best = True
    ttl_hours = 6  # how long a result outlives the cycle that last refreshed it

    def accept(self, voters):
        """A rule-specific gate on the voting parents (one per family), before the bar on bits."""
        return True

    def groups(self, parents, ctx):
        """[Group] from the fresh layer-1 rows `parents`. `ctx` is whatever the runner loaded for
        the rule (owner maps and the like); rules must not read the database themselves."""
        raise NotImplementedError

    def observed(self, group):
        """The observed state recorded on the result (default: the anchor's)."""
        return group.anchor.observed

    def expected(self, group):
        return group.anchor.expected


def _parent_ref(parent):
    ref = {
        "id": getattr(parent, "row_id", None),
        "signal": parent.signal,
        "subject_id": parent.subject_id,
        "p": parent.probability,
        "confidence": parent.confidence,
        "family": family_of(parent),
    }
    if (parent.evidence or {}).get("feature"):
        ref["feature"] = parent.evidence["feature"]
    return ref


def fuse(rule, group, now):
    """The layer-2 Inference for one group, or None if it is not surprising enough."""
    families = {}
    for parent in group.parents:
        family = family_of(parent)
        if family is None or parent.probability is None:
            continue
        best = families.get(family)
        if best is None or parent.probability < best.probability:
            families[family] = parent
    voters = list(families.values())
    if not voters:
        return None
    ps = [max(p.probability, 1e-12) for p in voters]
    cs = [max(p.confidence or 0.0, 1e-6) for p in voters]
    p_comb = ps[0]
    if not rule.accept(voters):
        return None
    if len(voters) > 1:
        p_comb = max(fisher_p(ps, cs), 1e-12)
        if rule.cap_at_best:
            p_comb = min(min(ps), p_comb)
    surprise = -math.log2(p_comb)
    if group.explained_by:
        surprise *= 1.0 - rule.explained_discount
        p_comb = 2.0**-surprise
    if surprise < rule.min_bits:
        return None
    confidence = sum(cs) / len(cs)
    if group.share is not None:
        confidence *= rule.corroboration_floor + (1.0 - rule.corroboration_floor) * group.share
    anchor = group.anchor
    evidence = {
        "method": "fisher_by_family" if len(voters) > 1 else "single_family",
        "families": sorted(families),
        "parents": [_parent_ref(p) for p in group.parents],
        "corroboration": None if group.share is None else round(group.share, 3),
    }
    if group.explained_by:
        evidence["explained_by"] = [_parent_ref(p) for p in group.explained_by]
    evidence.update(group.evidence)
    return Inference(
        layer=2,
        kind="deviation",
        subject_type=rule.subject_type,
        subject_id=group.subject_id,
        signal=rule.signal,
        learner=rule.name,
        learner_version=rule.version,
        window_start=group.window_start or anchor.window_start,
        window_end=now.replace(microsecond=0),
        context=anchor.context,
        observed=rule.observed(group),
        expected=rule.expected(group),
        probability=round(p_comb, 12),
        surprise=round(surprise, 3),
        confidence=round(confidence, 4),
        n_eff=anchor.n_eff,
        evidence=evidence,
        expires_at=now + timedelta(hours=rule.ttl_hours),
    )


def run_rules(rules, parents, ctx, now):
    """Every layer-2 inference the rules find among the fresh layer-1 `parents`."""
    found = []
    for rule in rules:
        for group in rule.groups(parents, ctx):
            inference = fuse(rule, group, now)
            if inference is not None:
                found.append(inference)
    return found
