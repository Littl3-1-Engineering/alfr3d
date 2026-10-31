"""Stay-length learner (sa/learners/stay.py): an overstay is a long stay for THIS person, so a
part-time resident whose stays are long and scattered is never an anomaly."""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "service_sa"))

from sa.learners import stay  # noqa: E402

REF = date(2026, 10, 9)


def _intervals(durations_hours, arrive_hour=9):
    """One stay per day ending before REF, arriving at `arrive_hour` UTC-4 (13:00 UTC)."""
    out = []
    for i, hours in enumerate(durations_hours):
        start = datetime(2026, 10, 8) - timedelta(days=i) + timedelta(hours=arrive_hour + 4)
        out.append((start, start + timedelta(hours=hours), 100))
    return sorted(out)


def _profile(durations_hours, **kw):
    return stay.StayLearner().fit_user(
        1, "x", _intervals(durations_hours), REF, kw.get("coverage", 0.95), 0.8, 1.0
    )


def _score(profile, stay_hours, arrive_hour=9):
    start = datetime(2026, 10, 9) + timedelta(hours=arrive_hour + 4)
    return stay.StayLearner().score(
        profile, {"stay_start": start}, start + timedelta(hours=stay_hours)
    )


class TestStayLearner:
    def test_a_stay_far_longer_than_this_persons_usual_is_flagged(self):
        # Needs enough history to reach 5 bits: the most surprise n comparable stays can give is log2(n).
        profile = _profile([2, 3, 2, 3, 2, 3, 2, 2, 3, 2, 3, 2, 3, 2, 2, 3, 2, 3] * 3)

        found = _score(profile, 9)

        assert found is not None
        assert found.surprise >= stay.MIN_SURPRISE_BITS
        assert found.observed["state"] == "home"

    def test_a_long_stay_is_normal_for_someone_whose_stays_are_long_and_scattered(self):
        profile = _profile([3, 9, 20, 5, 14, 30, 8, 2, 25, 12, 6, 18, 10, 40, 4, 22, 7, 16])

        assert _score(profile, 9) is None

    def test_a_stay_shorter_than_the_minimum_is_never_scored(self):
        profile = _profile([2, 3] * 9)

        assert _score(profile, 0.5) is None

    def test_too_little_history_gives_no_profile(self):
        assert _profile([2, 3, 2]) is None

    def test_a_stay_is_judged_only_against_stays_that_began_at_a_similar_time(self):
        profile = _profile([2, 3] * 30, arrive_hour=9)

        assert _score(profile, 9, arrive_hour=9) is not None
        # Nothing in the history began at 02:00, so there is nothing comparable to be surprised by.
        assert _score(profile, 9, arrive_hour=2) is None

    def test_current_stay_start_follows_the_live_offline_lag(self):
        ivs = [(datetime(2026, 10, 9, 10), datetime(2026, 10, 9, 12), 50)]

        assert stay.current_stay_start(ivs, datetime(2026, 10, 9, 12, 20)) == ivs[0][0]
        assert stay.current_stay_start(ivs, datetime(2026, 10, 9, 13, 0)) is None
        assert stay.current_stay_start(ivs, datetime(2026, 10, 9, 9, 0)) is None


class TestStayStartFromSightings:
    def test_it_walks_back_over_gaps_silver_would_merge(self):
        t0 = datetime(2026, 10, 9, 8, 0)
        sightings = [t0, t0 + timedelta(minutes=40), t0 + timedelta(minutes=80)]

        assert stay.stay_start_from_sightings(sightings) == t0

    def test_a_gap_longer_than_the_merge_limit_starts_a_new_stay(self):
        t0 = datetime(2026, 10, 9, 8, 0)
        sightings = [t0, t0 + timedelta(hours=3), t0 + timedelta(hours=3, minutes=1)]

        assert stay.stay_start_from_sightings(sightings) == t0 + timedelta(hours=3)

    def test_no_sightings_means_no_stay(self):
        assert stay.stay_start_from_sightings([]) is None


class TestStability:
    """Stability is measured, not defaulted: how well stays before a window predicted the window."""

    def _fit(self, durations):
        return stay.StayLearner().fit_user(1, "x", _intervals(durations), REF, 0.95, 0.8)

    def test_steady_stays_are_stable(self):
        assert self._fit([2, 3] * 30).stability >= 0.9

    def test_a_recent_change_in_how_long_stays_last_lowers_it(self):
        # the last 14 stays are 12 h against two months of 2-3 h ones
        shifted = self._fit([12] * 14 + [2, 3] * 20)

        assert shifted.stability < 0.2
        assert shifted.stability < self._fit([2, 3] * 30).stability

    def test_too_few_stays_to_measure_leave_it_unknown(self):
        assert self._fit([2, 3] * 8).stability == stay.STABILITY_UNKNOWN

    def test_a_passed_in_stability_is_kept(self):
        profile = stay.StayLearner().fit_user(1, "x", _intervals([2, 3] * 30), REF, 0.95, 0.8, 0.42)

        assert profile.stability == 0.42
