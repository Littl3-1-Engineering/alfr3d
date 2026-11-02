"""The learned presence bridge (sa/presence_bridge.py, sa/learners/bridge.py) and the code that
uses it live: the stay start follows each person's own bridge, and a walk longer than it starts a
new stay even though the person never went offline long enough for user.state to notice."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "service_sa"))

from sa import presence_bridge  # noqa: E402
from sa.learners import bridge, household_day, stay  # noqa: E402
from sa.learners.base import Profile  # noqa: E402

T = datetime(2026, 10, 30, 12, 0)


class TestDecide:
    def test_too_few_nights_keep_the_default(self):
        assert presence_bridge.decide([30] * 20, nights=5) == (45, "default")

    def test_a_phone_that_hardly_naps_gets_the_floor(self):
        assert presence_bridge.decide([20, 30], nights=28) == (15, "quiet_phone")

    def test_a_napping_phone_gets_a_high_quantile_of_its_naps_rounded_up(self):
        naps = [12] * 40 + [30] * 40 + [37] * 15 + [52] * 5
        minutes, basis = presence_bridge.decide(naps, nights=28)
        assert basis == "naps" and minutes == 40  # the 95th percentile is 37, rounded up to 5

    def test_the_bridge_never_exceeds_the_ceiling(self):
        assert presence_bridge.decide([55, 58, 59] * 10, nights=28)[0] == 60

    def test_gaps_that_are_not_naps_are_ignored(self):
        # 5 min is arp skipping a device, 3 h is the person being out
        assert presence_bridge.decide([5] * 50 + [180] * 50, nights=28) == (15, "quiet_phone")

    def test_bridge_for_falls_back_and_accepts_either_key_type(self):
        assert presence_bridge.bridge_for({"7": 25}, 7) == 25
        assert presence_bridge.bridge_for({7: 25}, "7") == 45  # keys are matched as given or as str
        assert presence_bridge.bridge_for({}, 3) == 45
        assert presence_bridge.bridge_for(None, 3) == 45


class TestProfiles:
    def test_profiles_round_trip_to_a_bridge_map(self):
        profiles = bridge.profiles_from_rows(
            [(1, 40, "naps", 77, 25), (5, 15, "quiet_phone", 2, 25)]
        )

        assert bridge.bridges_from_profiles(profiles) == {"1": 40, "5": 15}

    def test_other_learners_profiles_are_ignored(self):
        other = Profile("stay_profile", "1", "user", 9, "presence.stay", {"stays": []})
        profiles = bridge.profiles_from_rows([(1, 40, "naps", 77, 25)])

        assert bridge.bridges_from_profiles([*profiles, other]) == {"1": 40}


class TestStayState:
    def test_a_gap_over_the_bridge_starts_a_new_stay(self):
        sightings = [T, T + timedelta(minutes=1), T + timedelta(minutes=30)]

        assert stay.stay_state(sightings, 15)[0] == T + timedelta(minutes=30)
        assert stay.stay_state(sightings, 45)[0] == T

    def test_it_continues_from_a_cached_state_over_newer_sightings_only(self):
        start, seen = stay.stay_state([T, T + timedelta(minutes=2)], 15)

        start, seen = stay.stay_state(
            [T + timedelta(minutes=2), T + timedelta(minutes=30)], 15, start, seen
        )

        assert start == T + timedelta(minutes=30)  # the walk ended the old stay
        assert seen == T + timedelta(minutes=30)

    def test_a_cached_stay_survives_a_gap_within_the_bridge(self):
        start, seen = stay.stay_state([T], 45)

        start, seen = stay.stay_state([T + timedelta(minutes=40)], 45, start, seen)

        assert start == T

    def test_no_sightings_means_no_stay(self):
        assert stay.stay_state([], 45) == (None, None)
        assert stay.stay_start_from_sightings([]) is None


class TestHomeMinutesPerPerson:
    def test_each_person_is_measured_with_their_own_bridge(self):
        # both are seen 12:00-12:10 and 12:35-12:45: a 25 minute gap
        seen = [T + timedelta(minutes=m) for m in (0, 10, 35, 45)]
        window = (T, T + timedelta(hours=1))

        both = household_day.home_minutes({1: seen, 5: seen}, *window, {1: 40, 5: 15})
        only_napper = household_day.home_minutes({1: seen}, *window, {1: 40, 5: 15})
        only_walker = household_day.home_minutes({5: seen}, *window, {1: 40, 5: 15})

        assert only_napper == 45  # one stay 12:00-12:45
        assert only_walker == 20  # two stays of 10 minutes
        assert both == 65

    def test_a_plain_number_still_works_for_everybody(self):
        seen = [T, T + timedelta(minutes=10), T + timedelta(minutes=35)]

        assert household_day.home_minutes({1: seen}, T, T + timedelta(hours=1), 45) == 35
