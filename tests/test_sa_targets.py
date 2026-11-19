"""The derived-target registry (sa/targets.py). The shipped registry must be sound, and every way
of registering a bad target must be rejected: wrong kind, a restricted or text or unknown feature,
over-budget candidates, a query that leaks the future or returns the wrong shape."""

from dataclasses import replace

from services.service_sa.sa import context_registry, targets

BY_KEY = {t.key: t for t in targets.REGISTRY}


class TestShippedRegistry:
    def test_it_is_sound(self):
        assert targets.validate() == []
        assert targets.validate_queries() == []

    def test_the_three_proof_targets_are_declared(self):
        assert set(BY_KEY) == {"guests_home", "house_empty", "away_minutes"}
        assert BY_KEY["guests_home"].kind == targets.COUNT
        assert BY_KEY["house_empty"].kind == targets.BINARY
        assert BY_KEY["away_minutes"].kind == targets.CONTINUOUS

    def test_every_target_fits_the_per_target_budget(self):
        for t in targets.REGISTRY:
            assert 0 < len(targets.expanded(t)) <= targets.MAX_PER_TARGET, t.key

    def test_sparse_kinds_use_the_rate_screen_and_continuous_the_slope_screen(self):
        assert targets.method_for(BY_KEY["guests_home"]) == "rates"
        assert targets.method_for(BY_KEY["house_empty"]) == "rates"
        assert targets.method_for(BY_KEY["away_minutes"]) == "slope"

    def test_no_target_offers_a_restricted_feature(self):
        restricted = {
            f.key for f in context_registry.REGISTRY if f.privacy == context_registry.RESTRICTED
        }
        for t in targets.REGISTRY:
            assert not restricted & {c.feature for c in t.candidates}, t.key


class TestValuesOnTheSyntheticLake:
    """The synthetic lake has an owner away 09-17, a resident away 08-12, a guest home 18-22 and a
    second guest home at hour 20 only; the expected values follow from that."""

    def _by_hour(self, key):
        con = targets.synthetic_lake()
        return {t.hour: v for t, v in targets.values(con, BY_KEY[key])[:24]}

    def test_guests_home(self):
        v = self._by_hour("guests_home")
        assert v[19] == 1.0 and v[20] == 2.0 and v[10] == 0.0

    def test_house_empty(self):
        v = self._by_hour("house_empty")
        # the owner is away 9-17 and the resident 8-12: both away only at hours 9 to 12
        assert [h for h in range(24) if v[h] == 1.0] == [9, 10, 11, 12]
        assert v[8] == 0.0 and v[13] == 0.0

    def test_away_minutes(self):
        v = self._by_hour("away_minutes")
        assert v[10] == 120.0  # owner and resident both away
        assert v[14] == 60.0  # only the owner
        assert v[3] == 0.0


def _only(target, **changes):
    return [replace(target, **changes)]


class TestValidateRejects:
    base = BY_KEY["house_empty"]

    def test_a_duplicate_key(self):
        assert any("duplicate target" in p for p in targets.validate([self.base, self.base]))

    def test_an_unknown_kind_and_a_non_household_scope(self):
        assert any("unknown kind" in p for p in targets.validate(_only(self.base, kind="rate")))
        assert any(
            "household-scoped" in p
            for p in targets.validate(_only(self.base, privacy=context_registry.OWNER_OPENED))
        )

    def test_a_restricted_feature_is_never_offered(self):
        bad = targets.Candidate("precise_location", (0,))
        problems = targets.validate(_only(self.base, candidates=(bad,)))
        assert any("not visible to a learner" in p for p in problems)

    def test_a_text_or_unknown_feature(self):
        for feature, expect in (("season", "not numeric"), ("no_such_thing", "unknown feature")):
            problems = targets.validate(
                _only(self.base, candidates=(targets.Candidate(feature, (0,)),))
            )
            assert any(expect in p for p in problems), feature

    def test_over_budget_and_duplicates(self):
        wide = (targets.Candidate("outdoor_temp_c", tuple(range(12)), targets.ANOMALY),)
        assert any(
            "over the budget" in p for p in targets.validate(_only(self.base, candidates=wide))
        )
        twice = (targets.Candidate("is_holiday", (0, 0)),)
        assert any(
            "offered twice" in p for p in targets.validate(_only(self.base, candidates=twice))
        )

    def test_bad_lags_and_transforms(self):
        bad = (targets.Candidate("is_holiday", (-1,)), targets.Candidate("is_daylight", (0,), "z"))
        problems = targets.validate(_only(self.base, candidates=bad))
        assert any("non-negative" in p for p in problems)
        assert any("unknown transform" in p for p in problems)

    def test_a_feature_is_offered_only_if_the_owner_opened_it(self):
        gated = [
            replace(f, privacy=context_registry.OWNER_OPENED) if f.key == "outdoor_temp_c" else f
            for f in context_registry.REGISTRY
        ]
        t = BY_KEY["house_empty"]
        assert any(
            "not visible" in p for p in targets.validate([t], features=gated, opened=frozenset())
        )
        assert targets.validate([t], features=gated, opened=frozenset({"outdoor_temp_c"})) == []


class TestValidateQueriesRejects:
    base = BY_KEY["away_minutes"]

    def test_a_query_that_does_not_run(self):
        problems = targets.validate_queries(_only(self.base, query="SELECT nope FROM nowhere"))
        assert any("query failed" in p for p in problems)

    def test_the_wrong_columns(self):
        q = "SELECT bucket_utc, minutes_home FROM g_presence_grid"
        assert any(
            "must return (bucket_utc, value)" in p
            for p in targets.validate_queries(_only(self.base, query=q))
        )

    def test_more_than_one_row_per_hour(self):
        q = "SELECT bucket_utc, minutes_home::DOUBLE AS value FROM g_presence_grid"
        assert any(
            "more than one row" in p for p in targets.validate_queries(_only(self.base, query=q))
        )

    def test_a_query_that_reads_the_future_is_caught(self):
        # the hour's value includes the average over ALL hours, so removing later hours changes it
        q = """SELECT bucket_utc,
                      AVG(minutes_home) OVER ()::DOUBLE AS value
               FROM (SELECT bucket_utc, SUM(minutes_home) AS minutes_home
                     FROM g_presence_grid GROUP BY bucket_utc)"""
        problems = targets.validate_queries(_only(self.base, query=q))
        assert any("leaks" in p for p in problems)


class TestCheckKind:
    def test_continuous_that_is_mostly_zero_is_rejected(self):
        t = BY_KEY["away_minutes"]
        assert "declare it count or binary" in targets.check_kind(t, [0.0] * 95 + [30.0] * 5)
        assert targets.check_kind(t, [0.0] * 40 + [30.0] * 60) is None

    def test_binary_and_count_must_fit(self):
        assert targets.check_kind(BY_KEY["house_empty"], [0, 1, 1, 0]) is None
        assert "other than 0 and 1" in targets.check_kind(BY_KEY["house_empty"], [0, 1, 2])
        assert targets.check_kind(BY_KEY["guests_home"], [0, 1, 2, 0]) is None
        assert "negative or fractional" in targets.check_kind(BY_KEY["guests_home"], [0, 1.5])
        assert "negative or fractional" in targets.check_kind(BY_KEY["guests_home"], [0, -1])

    def test_no_data_is_not_a_kind_problem(self):
        assert targets.check_kind(BY_KEY["guests_home"], []) is None
        assert targets.check_kind(BY_KEY["guests_home"], [None, None]) is None


def test_a_throwaway_target_is_one_registration():
    """Acceptance (prompt, Phase 4 spirit of Phase 2): a new outcome is one Target and a validation
    run, with no learner or SQL edit elsewhere."""
    throwaway = targets.Target(
        key="owner_away_minutes",
        kind=targets.CONTINUOUS,
        query="""WITH u AS (SELECT DISTINCT user_id, user_type FROM s_presence_intervals)
                 SELECT g.bucket_utc, (60 - g.minutes_home)::DOUBLE AS value
                 FROM g_presence_grid g JOIN u USING (user_id)
                 WHERE g.observed AND u.user_type = 'owner' ORDER BY g.bucket_utc""",
        description="The owner's minutes away in the hour.",
        candidates=(targets.Candidate("outdoor_temp_c", (0, 3), targets.ANOMALY),),
    )
    registry = targets.REGISTRY + (throwaway,)
    assert targets.validate(registry) == []
    assert targets.validate_queries(registry) == []
