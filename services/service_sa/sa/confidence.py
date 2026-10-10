"""Confidence, defined once (LF-3, todo/sa/SA_ROADMAP.md).

Every layer-1 inference carries a probability (what the model believes) and a confidence (how
much that belief deserves trusting). They answer different questions: a model can be 99% sure
Athos is home on a Friday morning and still have only a week of data behind that. Layer-2
inferences combine layer-1 ones weighted by this number, so it has to mean the same thing
everywhere. Hence one function, here, and not one per learner.

    confidence = sufficiency x coverage x source_quality x stability

each term in [0, 1]:

- sufficiency    : how much evidence backs this particular cell/estimate. Grows with the
                   (recency-weighted) number of observations W as W / (W + K): 0 with none, 0.5
                   when W equals K, approaching 1.
- coverage       : the share of the recent period the collector was actually running. A model
                   fitted on a month with a collection outage is less trustworthy than the same
                   model on a healthy month, whatever the sample count says.
- source_quality : how reliable the underlying signal is for THIS subject. For presence, how
                   densely their phone is sighted while they're home: a phone that sleeps its
                   radio shows up in fewer minutes than it is present.
- stability      : how well the model predicted the recent past. Lowered when it has been
                   surprised repeatedly lately, which means the regime changed (a new job, a
                   house move) and the old pattern is no longer a safe baseline.

The terms multiply, deliberately: any one of them being near zero should sink the whole thing,
and a product is the simplest rule with that property. There is no hidden weighting to tune.
"""

# Observations needed for sufficiency to reach 0.5. A weekday-hour cell collects one observation
# per matching day, so K = 3 means "about three comparable days of history".
SUFFICIENCY_HALF_WEIGHT = 3.0


def sufficiency(weight, half_weight=SUFFICIENCY_HALF_WEIGHT):
    """W / (W + K). `weight` is the recency-weighted count of observations (0 if none)."""
    if weight is None or weight <= 0:
        return 0.0
    return weight / (weight + half_weight)


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


class Confidence:
    """The four terms and their product. Every term is required: a missing one must never
    silently count as 1.0 (that would manufacture certainty out of absent information)."""

    TERMS = ("sufficiency", "coverage", "source_quality", "stability")

    def __init__(self, sufficiency, coverage, source_quality, stability):
        for name, value in zip(self.TERMS, (sufficiency, coverage, source_quality, stability)):
            if value is None:
                raise ValueError(f"confidence term '{name}' is missing")
        self.sufficiency = _clamp(sufficiency)
        self.coverage = _clamp(coverage)
        self.source_quality = _clamp(source_quality)
        self.stability = _clamp(stability)

    @property
    def value(self):
        return self.sufficiency * self.coverage * self.source_quality * self.stability

    def as_dict(self):
        terms = {name: round(getattr(self, name), 4) for name in self.TERMS}
        terms["value"] = round(self.value, 4)
        return terms
