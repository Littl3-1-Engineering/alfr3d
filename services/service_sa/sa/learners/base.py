"""The two plain records every learner exchanges with the rest of the system, and the interface
learners implement (LF-3, todo/sa/SA_ROADMAP.md).

A learner has two halves that run in different containers on purpose:

    fit(...)   slow. Reads the gold layer in the Parquet lake and produces Profiles. Runs in
               sa-learner, which owns the lake. Profiles are stored in MySQL (sa_profiles).
    score(...) fast. Compares the present against a stored Profile and produces Inferences.
               Cheap arithmetic only, no lake access, no long queries. Runs in sa-awareness,
               which is the 60-second card loop and must stay snappy.

Both halves live in one class, in one file, so the profile format a learner writes and the
scorer that reads it are always the same version.

Profile and Inference mirror the sa_profiles / sa_inferences tables (migration 046). No type
hints, per AGENTS.md.
"""

from datetime import datetime, timezone


def utcnow():
    """Naive UTC datetime, the convention of every timestamp in the SA tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Profile:
    """What a learner fitted for one subject: replaced wholesale on each fit."""

    def __init__(
        self,
        learner,
        learner_version,
        subject_type,
        subject_id,
        signal,
        params,
        n_eff=None,
        coverage=None,
        source_quality=None,
        stability=None,
        fitted_from=None,
        fitted_to=None,
        computed_at=None,
    ):
        self.learner = learner
        self.learner_version = learner_version
        self.subject_type = subject_type
        self.subject_id = str(subject_id)
        self.signal = signal
        self.params = params
        self.n_eff = n_eff
        self.coverage = coverage
        self.source_quality = source_quality
        self.stability = stability
        self.fitted_from = fitted_from
        self.fitted_to = fitted_to
        self.computed_at = computed_at or utcnow()


class Inference:
    """One scored statement about a subject over a window. See migration 046 for what
    `probability` means for each `kind`."""

    def __init__(
        self,
        kind,
        subject_type,
        subject_id,
        signal,
        learner,
        learner_version,
        window_start,
        window_end=None,
        context=None,
        observed=None,
        expected=None,
        probability=None,
        surprise=None,
        confidence=None,
        n_eff=None,
        evidence=None,
        layer=1,
        computed_at=None,
        expires_at=None,
    ):
        self.layer = layer
        self.kind = kind
        self.subject_type = subject_type
        self.subject_id = str(subject_id)
        self.signal = signal
        self.learner = learner
        self.learner_version = learner_version
        self.window_start = window_start
        self.window_end = window_end
        self.context = context
        self.observed = observed
        self.expected = expected
        self.probability = probability
        self.surprise = surprise
        self.confidence = confidence
        self.n_eff = n_eff
        self.evidence = evidence
        self.computed_at = computed_at or utcnow()
        self.expires_at = expires_at


class Learner:
    """Interface. Subclasses set `name`/`version` and implement fit() and score(). Bumping
    `version` when the profile format or maths changes lets a reader tell old rows from new."""

    name = ""
    version = ""

    def fit(self, *args, **kwargs):
        raise NotImplementedError

    def score(self, profile, state, now):
        raise NotImplementedError
