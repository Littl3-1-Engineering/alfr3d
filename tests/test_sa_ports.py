"""Tests for the learners that replace the legacy baselines (device rhythm, household day) and the
shadow runner that compares them with the legacy rules (sa/shadow.py)."""

import random
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock


from services.service_sa.sa import shadow
from services.service_sa.sa.learners import device_rhythm, household_day, rates, scalar

REF = date(2026, 10, 9)  # a Friday


def _rows(days, online_when):
    """(date, hour, dow, minutes_online, observed) rows for `days` days ending at REF."""
    rows, d = [], REF - timedelta(days=days - 1)
    while d <= REF:
        for h in range(24):
            rows.append((d, h, d.weekday(), 60.0 if online_when(d, h) else 0.0, True))
        d += timedelta(days=1)
    return rows


def _sessions(days, minutes_fn):
    out, d = [], REF - timedelta(days=days - 1)
    while d <= REF:
        out.append((d, minutes_fn(d), datetime.combine(d, datetime.min.time())))
        d += timedelta(days=1)
    return out


class TestDeviceRhythm:
    def _profile(self):
        rows = _rows(40, lambda d, h: 8 <= h < 22)
        sessions = _sessions(40, lambda d: 840 + (d.day % 5) * 10)
        return device_rhythm.DeviceRhythmLearner().fit_device(7, "Lamp", rows, sessions, REF, None)

    def test_a_device_with_no_recent_sessions_gets_no_profile(self):
        rows = _rows(40, lambda d, h: False)
        assert device_rhythm.DeviceRhythmLearner().fit_device(7, "x", rows, [], REF, None) is None

    def test_on_in_the_small_hours_is_unusual_hour(self):
        profile = self._profile()
        now = datetime(2026, 10, 10, 7, 0)
        inf = device_rhythm.DeviceRhythmLearner().score(
            profile,
            {"online": True, "offline_minutes": None, "local_dt": datetime(2026, 10, 10, 3, 0)},
            now,
        )
        assert inf is not None and inf.signal == "device.online"
        assert inf.expected["p_online"] < 0.15 and inf.surprise >= 3

    def test_off_when_normally_on_is_expected_absent_but_only_after_an_hour(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        local = datetime(2026, 10, 10, 14, 0)
        now = datetime(2026, 10, 10, 18, 0)
        assert (
            learner.score(profile, {"online": False, "offline_minutes": 20, "local_dt": local}, now)
            is None
        )
        inf = learner.score(
            profile, {"online": False, "offline_minutes": 90, "local_dt": local}, now
        )
        assert inf.observed["state"] == "offline"

    def test_a_device_offline_for_days_or_retired_is_not_late(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        local, now = datetime(2026, 10, 10, 14, 0), datetime(2026, 10, 10, 18, 0)
        state = {"online": False, "offline_minutes": 5 * 24 * 60, "local_dt": local}
        assert learner.score(profile, state, now) is None
        rows = _rows(40, lambda d, h: 8 <= h < 22)
        old = [(d, m, end - timedelta(days=30)) for d, m, end in _sessions(40, lambda d: 840)]
        assert learner.fit_device(7, "Old", rows, old, REF, None) is None

    def test_normal_state_is_quiet(self):
        profile = self._profile()
        inf = device_rhythm.DeviceRhythmLearner().score(
            profile,
            {"online": True, "offline_minutes": None, "local_dt": datetime(2026, 10, 10, 14, 0)},
            datetime(2026, 10, 10, 18, 0),
        )
        assert inf is None

    def test_a_session_far_longer_than_any_past_one_fires(self):
        profile, learner = self._profile(), device_rhythm.DeviceRhythmLearner()
        now = datetime(2026, 10, 10, 18, 0)
        local = datetime(2026, 10, 10, 14, 0)
        assert learner.score_duration(profile, {"minutes_on": 850, "local_dt": local}, now) is None
        inf = learner.score_duration(profile, {"minutes_on": 3000, "local_dt": local}, now)
        assert inf is not None and inf.observed["minutes_on"] == 3000 and inf.probability < 0.02

    def test_survival_is_smoothed_away_from_zero_and_one(self):
        d = [(100.0, 1.0)] * 10
        assert 0 < device_rhythm.survival(d, 10_000) < 0.1
        assert device_rhythm.survival(d, 0) < 1


class TestHouseholdDay:
    def _days(self, n=170, share=lambda d: 0.75, first=lambda d: 230.0, home=None):
        """A long history: an empirical tail cannot be smaller than about 1 / (days + 1), so the
        rule's bar is only reachable with a few months of days, as in production."""
        out, d = [], REF - timedelta(days=n - 1)
        rnd = random.Random(3)
        while d <= REF:
            day = {
                "date": d,
                "devices": 26,
                "device_share": share(d) + rnd.choice([-0.03, 0, 0, 0.03]),
                "first_minute": first(d) + rnd.choice([-10, 0, 10]),
            }
            if home:
                day["home_minutes"] = home(d) + rnd.choice([-60, 0, 60])
            out.append(day)
            d += timedelta(days=1)
        return out

    def _score(self, profile, share, first, home=None):
        state = {
            "device_share": share,
            "first_minute": first,
            "home_minutes": home,
            "local_dt": datetime(
                2026, 10, 13, 18, 0
            ),  # a Tuesday: holidays have few comparable days
        }
        return household_day.HouseholdDayLearner().score(
            profile, state, datetime(2026, 10, 13, 22, 0)
        )

    def test_too_little_history_gives_no_profile(self):
        assert household_day.HouseholdDayLearner().fit_days(self._days(10), REF) is None

    def test_a_normal_day_is_quiet(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        assert self._score(profile, 0.75, 230) is None

    def test_a_day_odd_on_both_features_is_a_layer_2_deviation_with_its_parents(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        inf = self._score(profile, 0.3, 700)
        assert inf.layer == 2 and inf.signal == "household.day"
        assert {p["feature"] for p in inf.evidence["parents"]} == {"device_share", "first_minute"}
        assert inf.surprise >= profile.params["calibration"]["bar_bits"] and 0 < inf.confidence <= 1

    def test_the_bar_is_learned_from_the_households_own_days(self):
        learner = household_day.HouseholdDayLearner()
        days = self._days()
        profile = learner.fit_days(days, REF)
        calibration = profile.params["calibration"]

        assert calibration["days"] >= household_day.MIN_CALIBRATION_DAYS
        assert calibration["target_rate"] == round(household_day.TARGET_FLAG_RATE, 4)
        weights = {d["date"]: 1.0 for d in days}
        bits = household_day.loo_bits(days, list(profile.params["features"]), weights)
        share = sum(b >= calibration["bar_bits"] for b in bits) / len(bits)
        # about one day in fourteen reaches the bar (ties in a discrete history widen it a little)
        assert 0.02 <= share <= household_day.TARGET_FLAG_RATE + 0.07

    def test_a_different_household_gets_a_different_bar(self):
        steady = household_day.HouseholdDayLearner().fit_days(self._days(), REF)
        erratic = household_day.HouseholdDayLearner().fit_days(
            self._days(share=lambda d: 0.4 + 0.1 * (d.toordinal() % 5)), REF
        )

        assert steady.params["calibration"]["bar_bits"] != erratic.params["calibration"]["bar_bits"]

    def test_with_too_little_history_there_is_no_bar_and_nothing_is_flagged(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(25), REF)

        assert profile.params["calibration"]["bar_bits"] is None
        assert self._score(profile, 0.05, 900) is None

    def test_event_streams_are_learned_as_features_when_they_vary_and_have_history(self):
        days = self._days()
        for i, day in enumerate(days):
            day["event:audio/track/play_start"] = float(40 + (i % 7))  # varies
            day["event:info/constant"] = 5.0  # never changes
            if i > len(days) - 10:
                day["event:new/stream/seen"] = float(i % 4)  # only ten days of history
        profile = household_day.HouseholdDayLearner().fit_days(days, REF)

        assert "event:audio/track/play_start" in profile.params["features"]
        assert "event:info/constant" not in profile.params["features"]
        assert "event:new/stream/seen" not in profile.params["features"]

    def test_an_odd_event_count_can_be_what_makes_the_day_unusual(self):
        days = self._days()
        for i, day in enumerate(days):
            day["event:audio/track/play_start"] = float(40 + (i % 7))
        learner = household_day.HouseholdDayLearner()
        profile = learner.fit_days(days, REF)
        state = {
            "device_share": 0.75,
            "first_minute": 230,
            "event:audio/track/play_start": 400.0,
            "local_dt": datetime(2026, 10, 13, 18, 0),
        }
        inf = learner.score(profile, state, datetime(2026, 10, 13, 22, 0))

        assert inf is not None
        assert inf.observed["event:audio/track/play_start"] == 400.0
        assert any("audio track play_start events" in line for line in household_day.explain(inf))

    def test_home_minutes_is_a_third_feature(self):
        learner = household_day.HouseholdDayLearner()
        profile = learner.fit_days(self._days(home=lambda d: 2600.0), REF)

        assert set(profile.params["features"]) == set(household_day.FEATURES)
        assert self._score(profile, 0.75, 230, home=2600) is None  # an ordinary day
        inf = self._score(profile, 0.3, 700, home=900)
        assert {p["feature"] for p in inf.evidence["parents"]} == set(household_day.FEATURES)
        assert inf.observed["home_minutes"] == 900

    def test_a_v1_profile_without_home_minutes_still_scores(self):
        profile = household_day.HouseholdDayLearner().fit_days(self._days(), REF)

        assert "home_minutes" not in profile.params["features"]
        assert self._score(profile, 12, 700, home=900) is not None

    def test_home_minutes_uses_silvers_stay_rule(self):
        t = datetime(2026, 10, 12, 8, 0)
        sightings = {
            1: [t + timedelta(minutes=m) for m in (0, 20, 40, 60)]  # one stay, 60 min
            + [t + timedelta(minutes=300)],  # a lone sighting later: zero length
            2: [t - timedelta(minutes=20), t + timedelta(minutes=20)],  # starts before window
        }
        window = (t, t + timedelta(hours=10))

        assert household_day.home_minutes(sightings, *window) == 60 + 20

    def test_a_gap_longer_than_the_stay_rule_splits_the_stay(self):
        t = datetime(2026, 10, 12, 8, 0)
        sightings = {1: [t, t + timedelta(minutes=30), t + timedelta(minutes=120)]}

        assert household_day.home_minutes(sightings, t, t + timedelta(hours=5)) == 30

    def test_empirical_tail_handles_a_bimodal_feature_a_gaussian_z_cannot(self):
        # First activity: a nightly reconnect at ~231 min on 60 % of days, an earlier phone nap on
        # the rest. 7 minutes is unusual but not 7 sigma from the 231 median.
        samples = [(231.0, 1.0)] * 60 + [(v, 1.0) for v in (5, 36, 70, 83, 87, 131, 140, 150) * 5]

        assert 0.05 < household_day.empirical_p(samples, 7.0) < 0.3
        assert household_day.empirical_p(samples, 231.0) == 1.0
        assert household_day.empirical_p(samples, -1000.0) < 0.05  # beyond all history

    def test_a_short_history_cannot_claim_certainty(self):
        assert household_day.empirical_p([(1.0, 1.0)] * 4, 99.0) >= 1.0 / 5.0

    def test_fisher_combines_mild_evidence(self):
        assert household_day.fisher_p([0.05, 0.05], [1, 1]) < 0.05
        assert household_day.fisher_p([0.5, 0.5], [1, 1]) > 0.5
        # low confidence weights the evidence down
        assert household_day.fisher_p([0.001, 0.001], [0.1, 0.1]) > household_day.fisher_p(
            [0.001, 0.001], [1, 1]
        )


class TestLiveRates:
    STREAM = "event:notification/sender/messaged"

    def _profile(self):
        pts = []
        for i in range(14 * 24):
            t = datetime(2026, 9, 1) + timedelta(hours=i)
            n = 3 if 9 <= t.hour < 17 else 0
            pts.append({"date": t.date(), "hour": t.hour, "n": n + (i % 3 == 0), "t": t})
        return rates.fit_stream(self.STREAM, "hour", pts, date(2026, 9, 14), {})

    def _runner(self, counts):
        cursor = MagicMock()
        cursor.fetchall.return_value = counts
        db = MagicMock()
        db.cursor.return_value = cursor
        persisted = []
        runner = shadow.ShadowRunner(lambda: db, persisted.extend)
        runner.profiles = lambda name: [self._profile()]
        return runner, persisted

    def _frame(self, minute=5):
        from types import SimpleNamespace
        from datetime import timezone

        # 14:05 Toronto on a Tuesday = 18:05 UTC: the hour that just ended is 13:00-14:00 local.
        return SimpleNamespace(
            now=datetime(2026, 10, 13, 18, minute, tzinfo=timezone.utc),
            local_dt=datetime(2026, 10, 13, 14, minute),
        )

    def test_an_unusual_burst_in_the_hour_that_just_ended_is_flagged_and_persisted(self):
        runner, persisted = self._runner([("notification", "sender", "messaged", 40)])

        found = runner.live_rates(self._frame())

        assert len(found) == 1 and persisted == found
        assert found[0].observed["direction"] == "high"
        assert found[0].window_start == datetime(2026, 10, 13, 17, 0)  # 13:00 local, UTC

    def test_a_normal_hour_is_quiet_and_a_missing_stream_counts_as_zero(self):
        runner, persisted = self._runner([("notification", "sender", "messaged", 3)])

        assert runner.live_rates(self._frame()) == [] and persisted == []

    def test_each_hour_is_scored_once_and_not_before_the_events_have_landed(self):
        runner, _ = self._runner([("notification", "sender", "messaged", 40)])

        assert runner.live_rates(self._frame(minute=1)) == []  # too early
        assert len(runner.live_rates(self._frame(minute=5))) == 1
        assert runner.live_rates(self._frame(minute=20)) == []  # already scored this hour


class TestShadowRunner:
    def _runner(self):
        persisted = []
        return shadow.ShadowRunner(MagicMock(), persisted.extend), persisted

    def test_logs_only_when_the_pair_changes(self, caplog):
        runner, _ = self._runner()
        caplog.set_level("INFO", logger="SALog")
        runner.record("climate_deviation", "quiet", [])
        runner.record("climate_deviation", "quiet", [])
        assert sum("SHADOW" in r.message for r in caplog.records) == 1
        runner.record("climate_deviation", "climate_deviation:", [])
        assert "DIFFER" in caplog.records[-1].message

    def test_findings_are_persisted_and_marked_agree_when_both_fire(self, caplog):
        runner, persisted = self._runner()
        caplog.set_level("INFO", logger="SALog")
        pts = [
            {
                "t": datetime(2026, 9, 1) + timedelta(hours=i),
                "date": (
                    date(2026, 9, 1) + timedelta(hours=i // 24 * 24 // 24)
                    if False
                    else (datetime(2026, 9, 1) + timedelta(hours=i)).date()
                ),
                "hour": (i % 24),
                "value": 20.0 + (i % 5) * 0.1,
                "coverage": 1.0,
            }
            for i in range(24 * 10)
        ]
        profile = scalar.fit_points("s", pts, pts[-1]["date"])
        inf = scalar.ScalarLearner().score(
            profile,
            {
                "value": 40.0,
                "recent": [(lag, (24 - lag) % 24, 20.2) for lag in range(1, 25)],
                "local_dt": datetime(2026, 9, 11, 3, 0),
            },
            datetime(2026, 9, 11, 3, 0),
        )
        assert inf is not None
        runner.record("climate_deviation", "climate_deviation:", [inf])
        assert persisted == [inf] and "AGREE" in caplog.records[-1].message

    def test_an_exception_in_a_comparison_never_escapes(self, caplog):
        runner, _ = self._runner()
        runner.climate = MagicMock(side_effect=RuntimeError("db down"))
        runner.run(MagicMock(), {"climate_deviation": None})
        assert any("SHADOW climate_deviation failed" in r.message for r in caplog.records)

    def test_only_rules_the_engine_ran_are_compared(self):
        runner, _ = self._runner()
        runner.climate = MagicMock(return_value=[])
        runner.run(MagicMock(), {"time": None})
        runner.climate.assert_not_called()

    def _stay_profile(self):
        from sa.learners import stay

        ivs = []
        for i in range(60):
            start = datetime(2026, 10, 8) - timedelta(days=i) + timedelta(hours=13)
            ivs.append((start, start + timedelta(hours=2 + i % 2), 100))
        return stay.StayLearner().fit_user(1, "athos", sorted(ivs), REF, 0.95, 0.8, 1.0)

    def _departure_runner(self, stay_start, user_type="owner", busy_event=None):
        from sa.learners import stay

        runner, _ = self._runner()
        profile = self._stay_profile()
        runner.profiles = lambda name: [profile] if name == stay.NAME else []
        cursor = MagicMock()
        cursor.fetchall.return_value = [(stay_start,), (stay_start + timedelta(minutes=30),)]
        cursor.fetchone.return_value = busy_event
        runner._connect = lambda: MagicMock(cursor=lambda: cursor)
        frame = MagicMock()
        frame.person_presence = [
            {"user_id": 1, "home": True, "user_type": user_type, "last_online": None}
        ]
        frame.local_dt = datetime(2026, 10, 9, 20, 0)
        frame.now = datetime(2026, 10, 9, 23, 30)  # 19:30 local; the stay began at 09:00 local
        return runner, frame

    def test_departure_flags_a_resident_whose_stay_is_far_longer_than_usual(self):
        runner, frame = self._departure_runner(datetime(2026, 10, 9, 13, 0))

        findings = runner.departure(frame)

        assert findings and findings[0].observed["state"] == "home"
        assert runner._stay_starts["1"] == datetime(2026, 10, 9, 13, 0)

    def test_departure_stays_quiet_while_a_calendar_event_covers_the_moment(self):
        runner, frame = self._departure_runner(datetime(2026, 10, 9, 13, 0), busy_event=(1,))

        assert runner.departure(frame) == []

    def test_departure_does_not_look_at_guests(self):
        runner, frame = self._departure_runner(datetime(2026, 10, 9, 13, 0), user_type="guest")

        assert runner.departure(frame) == []

    def test_departure_forgets_the_stay_when_the_person_leaves(self):
        runner, frame = self._departure_runner(datetime(2026, 10, 9, 13, 0))
        runner.departure(frame)
        frame.person_presence[0]["home"] = False

        runner.departure(frame)

        assert runner._stay_starts == {}

    def test_rhythm_ignores_an_offline_row_replaced_by_an_online_row_of_the_same_name(self):
        runner, _ = self._runner()
        profile = TestDeviceRhythm()._profile()
        profile.subject_id = "4"
        runner.profiles = lambda name: [profile]
        now = datetime(2026, 10, 10, 18, 0)
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (4, "offline", now - timedelta(hours=14), "Phone"),
            (137, "online", now - timedelta(minutes=1), "Phone"),
        ]
        runner._connect = lambda: MagicMock(cursor=lambda: cursor)
        frame = MagicMock()
        frame.local_dt, frame.now = datetime(2026, 10, 10, 14, 0), now
        assert runner.rhythm(frame) == []


class TestHouseholdDayAsRule:
    def _rows(self, share, first, home=None):
        learner = household_day.HouseholdDayLearner()
        days = TestHouseholdDay()._days(home=(lambda d: 2600.0) if home is not None else None)
        profile = learner.fit_days(days, REF)
        state = {
            "device_share": share,
            "first_minute": first,
            "home_minutes": home,
            "local_dt": datetime(2026, 10, 13, 18, 0),
        }
        return learner.score_features(profile, state, datetime(2026, 10, 13, 22, 0))

    def test_features_are_layer_one_state_rows_each_in_its_own_family(self):
        from services.service_sa.sa import layer2

        rows = self._rows(0.75, 230)  # an unremarkable day still yields rows

        assert {r.evidence["feature"] for r in rows} == {"device_share", "first_minute"}
        assert all(r.layer == 1 and r.kind == "state" and 0 < r.probability <= 1 for r in rows)
        assert len({layer2.family_of(r) for r in rows}) == 2

    def test_the_rule_flags_two_odd_features_and_matches_the_learner(self):
        from services.service_sa.sa import layer2

        rows = self._rows(0.3, 700)
        out = layer2.run_rules([household_day.RULE], rows, {}, datetime(2026, 10, 12, 22, 0))

        assert len(out) == 1 and out[0].layer == 2 and out[0].signal == "household.day"
        assert out[0].surprise >= rows[0].context["bar_bits"]
        assert out[0].observed == {"device_share": 0.3, "first_minute": 700}

    def test_a_normal_day_is_quiet_and_so_is_any_day_without_a_learned_bar(self):
        import copy

        from services.service_sa.sa import layer2

        now = datetime(2026, 10, 12, 22, 0)
        assert layer2.run_rules([household_day.RULE], self._rows(0.75, 230), {}, now) == []
        odd = copy.deepcopy(self._rows(0.3, 700))
        for row in odd:
            row.context["bar_bits"] = None
        assert layer2.run_rules([household_day.RULE], odd, {}, now) == []

    def test_every_row_fits_the_sa_inferences_columns(self):
        """Regression: subject_type 'household_feature' (17 chars) overflowed VARCHAR(16), so
        every household row failed to persist in production and the verdict never ran."""
        from services.service_sa.sa import layer2

        rows = self._rows(0.3, 700)
        out = layer2.run_rules([household_day.RULE], rows, {}, datetime(2026, 10, 12, 22, 0))

        for inference in [*rows, *out]:
            assert len(inference.subject_type) <= 16 and len(inference.signal) <= 48
            assert len(inference.subject_id) <= 64 and len(inference.learner) <= 48
            assert len(inference.learner_version) <= 16

    def test_the_live_day_is_measured_by_sightings_and_identities_like_the_fitted_days(self):
        """Regression: the live count used raw history rows (every state change writes one), so
        78 'devices' were scored against a profile of ~21 and every evening looked unusual."""
        tests = TestHouseholdDay()
        profile = household_day.HouseholdDayLearner().fit_days(tests._days(), REF)
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(26, datetime(2026, 10, 12, 7, 50)), (30,)]
        cursor.fetchall.return_value = []
        persisted = []
        runner = shadow.ShadowRunner(lambda: MagicMock(cursor=lambda: cursor), persisted.extend)
        runner.profiles = lambda name: [profile]
        frame = MagicMock()
        frame.now = datetime(2026, 10, 12, 22, 5)
        frame.local_dt = datetime(2026, 10, 12, 18, 5)
        frame.person_presence = [
            {"user_id": 1, "user_type": "owner"},
            {"user_id": 9, "user_type": "guest"},
        ]

        rows = runner.household(frame)

        sql, params = cursor.execute.call_args_list[0].args
        assert "last_online AS ts" in sql and "CONCAT('p', user_id" in sql
        assert 1 in params and 9 in params  # every person's rows merge by name, not just residents
        inventory_sql = cursor.execute.call_args_list[1].args[0]
        assert "COUNT(DISTINCT CASE WHEN user_id IN" in inventory_sql
        by_feature = {r.evidence["feature"]: r for r in rows}
        assert by_feature["device_share"].observed["value"] == round(26 / 30, 2)
        assert by_feature["first_minute"].observed["value"] == 230.0

    def test_household_rows_are_refreshed_before_each_persist(self):
        """Regression: cached rows were re-persisted with their creation time, so layer 2 (which
        reads rows refreshed in the last five minutes) stopped seeing them after five minutes."""
        persisted = []
        runner = shadow.ShadowRunner(MagicMock(), persisted.extend)
        rows = self._rows(0.3, 700)
        stale = datetime(2026, 1, 1)
        for row in rows:
            row.computed_at = stale
        runner.household = lambda frame: rows

        runner.household_features(MagicMock())

        assert persisted == rows and all(r.computed_at > stale for r in rows)

    def test_after_the_cutover_the_rule_has_no_legacy_card_to_compare_with(self):
        assert not hasattr(household_day.RULE, "legacy_rule")

    def test_the_card_explains_only_the_features_that_were_off(self):
        from services.service_sa.sa import layer2

        rows = self._rows(0.3, 700)
        now = datetime(2026, 10, 12, 22, 0)
        out = layer2.run_rules([household_day.RULE], rows, {}, now)[0]

        lines = household_day.explain(out)

        assert any(line.startswith("30% of the household's devices") for line in lines)
        assert any(line.startswith("first device online at 11:40") for line in lines)
        assert len(lines) == 2 and all("typically" in line for line in lines)


class TestShadowComparisonIsKept:
    """The comparison outlives the container log (sa_shadow_comparison, migration 048)."""

    def _runner(self):
        cursor = MagicMock()
        db = MagicMock()
        db.cursor.return_value = cursor
        return shadow.ShadowRunner(lambda: db, lambda inferences: None), cursor

    def _rows(self, cursor):
        return [
            c.args[1] for c in cursor.execute.call_args_list if "sa_shadow_comparison" in c.args[0]
        ]

    def test_a_change_of_outcome_is_saved_once(self):
        runner, cursor = self._runner()

        runner.record("climate_deviation", "quiet", [])
        runner.record("climate_deviation", "quiet", [])

        rows = self._rows(cursor)
        assert len(rows) == 1
        assert rows[0][0] == "climate_deviation"
        assert rows[0][2:] == ("AGREE", "quiet", "quiet", 0)

    def test_a_disagreement_is_saved_as_differ(self):
        runner, cursor = self._runner()
        finding = MagicMock(probability=0.01, confidence=0.5, expected={}, observed={})
        finding.evidence = {"series": "x"}

        runner.record("climate_deviation", "quiet", [finding])

        assert self._rows(cursor)[0][2] == "DIFFER"
        assert self._rows(cursor)[0][5] == 1

    def test_a_failed_save_does_not_break_the_cycle(self):
        runner, cursor = self._runner()
        cursor.execute.side_effect = RuntimeError("table missing")

        runner.record("climate_deviation", "quiet", [])
