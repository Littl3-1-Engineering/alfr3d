"""Tests for replay-versus-live parity (sa/parity.py): only matching-input days are compared, each
day's profile never sees that day, every kind of disagreement is reported, and a handful of quiet
days can never read as a pass.

Pure comparison logic is tested on hand-built records; the walk-forward on a synthetic lake whose
answer is known.
"""

from datetime import date, datetime, timedelta


from services.service_sa.sa import parity
from services.service_sa.sa.learners import presence
from services.service_sa.sa.learners.base import Inference, Profile
from tests.test_sa_replay import LAST, _worker, _write_lake

ZONE = parity._zone()


def _live(window_start, window_end, bits=5.0, confidence=0.5):
    return Inference(
        kind="deviation",
        subject_type="user",
        subject_id="1",
        signal="x",
        learner="x",
        learner_version="1",
        window_start=window_start,
        window_end=window_end,
        surprise=bits,
        confidence=confidence,
    )


def _strong(confidence=0.5):
    return {"bits": 5.0, "confidence": confidence, "n": 1}


DAYS = [date(2026, 11, 11) + timedelta(days=i) for i in range(5)]


class TestWindow:
    def test_window_runs_from_since_to_the_last_complete_day(self):
        out = parity.window(date(2026, 11, 1), date(2026, 11, 18), date(2026, 11, 14))

        assert out == (date(2026, 11, 1), date(2026, 11, 13))  # today is never complete

    def test_no_complete_day_since_the_date_is_no_window(self):
        assert parity.window(date(2026, 11, 18), date(2026, 11, 17), date(2026, 11, 19)) is None
        assert parity.window(date(2026, 11, 19), date(2026, 11, 19), date(2026, 11, 19)) is None

    def test_a_window_start_stamped_a_second_before_midnight_is_the_next_local_day(self):
        # 04:59:59 UTC is 23:59:59 the evening before in Toronto (EST): it means local midnight.
        assert parity.local_day(datetime(2026, 11, 14, 4, 59, 59), ZONE) == date(2026, 11, 14)
        assert parity.local_day(datetime(2026, 11, 14, 17, 0, 0), ZONE) == date(2026, 11, 14)

    def test_no_learner_compares_the_day_the_presence_bridge_was_deployed(self):
        # PR #365 landed during 2026-11-01, so that day's live profile predates it.
        assert all(d >= date(2026, 11, 2) for d in parity.MATCHING_INPUTS_SINCE.values())

    def test_the_stay_learner_compares_only_days_after_the_arrival_fix(self):
        assert parity.MATCHING_INPUTS_SINCE["stay_profile"] >= date(2026, 11, 19)

    def test_every_covered_learner_has_a_matching_inputs_date(self):
        assert set(parity.COVERED) <= set(parity.MATCHING_INPUTS_SINCE)


class TestLiveDays:
    def test_a_multi_day_row_covers_each_day_it_lived_in_the_window(self):
        rows = [_live(datetime(2026, 11, 10, 15, 0), datetime(2026, 11, 13, 15, 0))]

        out = parity.live_days(rows, date(2026, 11, 11), date(2026, 11, 12), ZONE)

        assert sorted(out) == [date(2026, 11, 11), date(2026, 11, 12)]  # clipped to the window

    def test_a_day_keyed_row_belongs_to_its_start_day_only(self):
        # Stamped a second before local midnight, last refreshed just after the next midnight.
        row = _live(datetime(2026, 11, 14, 4, 59, 59), datetime(2026, 11, 15, 5, 3, 30))

        spread = parity.live_days([row], DAYS[0], DAYS[-1], ZONE)
        keyed = parity.live_days([row], DAYS[0], DAYS[-1], ZONE, start_day_only=True)

        assert sorted(keyed) == [date(2026, 11, 14)]
        assert date(2026, 11, 15) in spread  # the spread reading is what mis-credits the next day

    def test_a_row_without_a_window_start_is_ignored(self):
        assert parity.live_days([_live(None, None)], DAYS[0], DAYS[-1], ZONE) == {}


class TestCompare:
    def test_agreeing_flags_and_quiet_days_match(self):
        out = parity.compare_days({DAYS[1]: _strong()}, {DAYS[1]: _strong()}, DAYS)

        assert out["outcomes"] == {
            "both": 1,
            "live_only": 0,
            "replay_only": 0,
            "borderline": 0,
            "neither": 4,
        }
        assert out["mismatches"] == [] and out["card_floor_flips"] == []

    def test_a_day_only_live_flagged_is_named(self):
        out = parity.compare_days({DAYS[1]: _strong()}, {}, DAYS)

        assert out["outcomes"]["live_only"] == 1
        assert out["mismatches"][0]["kind"] == "live_only"
        assert out["mismatches"][0]["day"] == "2026-11-12"

    def test_a_day_only_the_replay_flagged_is_named(self):
        out = parity.compare_days({}, {DAYS[2]: _strong()}, DAYS)

        assert out["mismatches"][0]["kind"] == "replay_only"

    def test_both_flagged_but_only_one_reaches_a_card_is_a_mismatch(self):
        out = parity.compare_days({DAYS[1]: _strong(0.35)}, {DAYS[1]: _strong(0.25)}, DAYS)

        assert out["card_floor_flips"] == ["2026-11-12"]

    def test_a_rule_without_a_confidence_is_never_a_card_floor_flip(self):
        out = parity.compare_days({DAYS[1]: _strong(None)}, {DAYS[1]: _strong(None)}, DAYS)

        assert out["card_floor_flips"] == []


class TestBorderline:
    def _bits(self, bits):
        return {"bits": bits, "confidence": 0.5, "n": 1}

    def test_a_one_sided_day_just_over_the_bar_is_borderline_not_a_mismatch(self):
        out = parity.compare_days({DAYS[1]: self._bits(3.2)}, {}, DAYS, bar=3.0)

        assert out["outcomes"]["borderline"] == 1 and out["outcomes"]["live_only"] == 0
        assert out["mismatches"] == [] and out["borderline"][0]["kind"] == "live_only"

    def test_a_one_sided_day_well_over_the_bar_is_still_a_mismatch(self):
        out = parity.compare_days({}, {DAYS[1]: self._bits(5.4)}, DAYS, bar=3.0)

        assert out["outcomes"]["replay_only"] == 1 and out["outcomes"]["borderline"] == 0
        assert out["mismatches"][0]["kind"] == "replay_only"

    def test_without_a_bar_nothing_is_borderline(self):
        out = parity.compare_days({DAYS[1]: self._bits(3.01)}, {}, DAYS)

        assert out["outcomes"]["live_only"] == 1 and out["borderline"] == []

    def test_borderline_days_are_reported_in_the_verdict_not_hidden(self):
        record = TestVerdict()._record(
            parity.MIN_SUBJECT_DAYS,
            outcomes={"both": 3, "live_only": 0, "replay_only": 0, "borderline": 2, "neither": 9},
        )

        assert "2 borderline" in parity.verdict([record])
        assert parity.verdict([record]).startswith("MATCH")


class TestVerdict:
    def _record(self, days, **overrides):
        record = {
            "comparable_days": days,
            "outcomes": {"both": 0, "live_only": 0, "replay_only": 0, "neither": days},
            "mismatches": [],
            "card_floor_flips": [],
        }
        record.update(overrides)
        return record

    def test_few_quiet_days_are_insufficient_never_a_pass(self):
        assert parity.verdict([self._record(3)]).startswith("INSUFFICIENT")

    def test_subject_days_are_pooled_across_people(self):
        records = [self._record(parity.MIN_SUBJECT_DAYS // 2) for _ in range(2)]

        assert parity.verdict(records).startswith("MATCH")

    def test_quiet_agreement_says_it_is_only_quiet_agreement(self):
        out = parity.verdict([self._record(parity.MIN_SUBJECT_DAYS)])

        assert out.startswith("MATCH (neither side flagged anything")

    def test_one_mismatch_is_a_mismatch(self):
        record = self._record(
            parity.MIN_SUBJECT_DAYS,
            mismatches=[{"day": "2026-11-12", "kind": "live_only"}],
        )

        assert parity.verdict([record]).startswith("MISMATCH: 1 day")

    def test_agreement_on_flagged_days_is_a_plain_match(self):
        record = self._record(
            parity.MIN_SUBJECT_DAYS,
            outcomes={"both": 2, "live_only": 0, "replay_only": 0, "neither": 12},
        )

        assert parity.verdict([record]) == "MATCH"


class TestProfileParity:
    def _profile(self, **kw):
        base = dict(n_eff=10.0, coverage=0.98, source_quality=0.8, stability=0.9)
        base.update(kw)
        return Profile("p", "1", "user", 1, "s", {}, **base)

    def test_identical_fits_agree(self):
        out = parity.profile_parity(self._profile(), self._profile())

        assert all(v["ok"] for v in out.values())
        assert out["stability"]["drift_capped"] is False

    def test_a_drift_capped_stability_is_expected_and_labelled(self):
        out = parity.profile_parity(self._profile(stability=0.4), self._profile())

        assert out["stability"]["ok"] and out["stability"]["drift_capped"]

    def test_a_stored_stability_above_the_refit_is_not_ok(self):
        out = parity.profile_parity(self._profile(stability=1.0), self._profile(stability=0.5))

        assert out["stability"]["ok"] is False

    def test_a_changed_sample_size_means_the_lake_moved_under_the_profile(self):
        out = parity.profile_parity(self._profile(n_eff=12.0), self._profile(n_eff=10.0))

        assert out["n_eff"]["ok"] is False


class TestWalkForward:
    def _absence_lake(self, tmp_path):
        def history(day, hour):
            if day == LAST and 9 <= hour < 17:
                return 0
            return 60

        return _write_lake(tmp_path, history)

    def test_an_unexpected_absence_is_found_on_its_own_day_only(self, tmp_path):
        lake = self._absence_lake(tmp_path)

        out = parity.walk_presence(lake, 1, LAST - timedelta(days=4), LAST)

        assert list(out) == [LAST]
        assert out[LAST]["bits"] >= presence.MIN_SURPRISE_BITS

    def test_each_day_is_scored_by_a_profile_that_has_not_seen_it(self, tmp_path):
        # A worker at home on one work day. Walk-forward refits through the day before, so the
        # day surprises the model; a profile that had already seen it is less surprised.
        def history(day, hour):
            return 60 if day == LAST else _worker(day, hour)

        lake = _write_lake(tmp_path, history)
        grid, intervals, users = presence.load_gold(lake)
        leaky = presence.PresenceLearner().fit_user(1, "athos", grid[1], intervals[1], LAST)
        walked = parity.walk_presence(lake, 1, LAST, LAST)

        assert walked[LAST]["bits"] >= presence.MIN_SURPRISE_BITS
        assert leaky.fitted_to == LAST  # the comparison profile did include the day

    def test_observed_days_exclude_days_the_collector_missed(self, tmp_path):
        lake = _write_lake(tmp_path, _worker)

        days = parity.observed_days(lake, 1, LAST - timedelta(days=2), LAST)

        assert days == [LAST - timedelta(days=2), LAST - timedelta(days=1), LAST]
        assert (
            parity.observed_days(lake, 1, LAST + timedelta(days=1), LAST + timedelta(days=3)) == []
        )


class TestCoverage:
    def _profile(self, subject_id, **params):
        return Profile("p", "1", "series", subject_id, "s", params)

    def test_scalar_compares_only_the_series_live_scores(self):
        keep = [
            "esphome:athom-tem-hum-sensor-4a4734.local:Temperature",
            "esphome:athom-tem-hum-sensor-4a4734.local:Humidity",
            "attention:switch_count",
            "attention:unlock_count",
        ]
        drop = [
            "ha:sensor.speedtest_ping",
            "deck:376a3c33:battery",
            "esphome:athom-tem-hum-sensor-4a4734.local:WiFi Signal dB",
        ]

        assert all(parity._select_scalar(None, self._profile(k))[0] for k in keep)
        assert not any(parity._select_scalar(None, self._profile(k))[0] for k in drop)
        assert "nightly" in parity._select_scalar(None, self._profile(drop[0]))[1]

    def test_rates_compares_only_hourly_event_streams(self):
        hourly = self._profile("event:x", window="hour", stream="event:play_start")
        daily = self._profile("sender:y", window="day", stream="sender:someone")
        email_hourly = self._profile("email", window="hour", stream="email_volume")

        assert parity._select_rates(None, hourly)[0]
        assert not parity._select_rates(None, daily)[0]
        assert not parity._select_rates(None, email_hourly)[0]

    def test_nightly_batch_rows_are_not_compared_with_a_walk_forward(self):
        hour = datetime(2026, 11, 5, 3)
        batch = _live(hour, hour + timedelta(hours=1))
        live = _live(hour, hour + timedelta(minutes=17))

        assert parity._batch_hour_rows([batch, live]) == [live]

    def test_every_covered_learner_declares_how_to_compare_itself(self):
        required = {"walk", "refit", "signal", "day_keyed", "subject", "days", "select"}

        assert all(required <= set(spec) for spec in parity.COVERED.values())
        assert set(parity.COVERED) == {
            "presence_profile",
            "stay_profile",
            "daytime_profile",
            "household_day",
            "scalar_baseline",
            "event_rate",
            "device_rhythm",
        }

    def test_the_device_rhythm_replay_is_declared_approximate(self):
        assert parity.COVERED["device_rhythm"].get("approximate") is True
        assert not any(
            spec.get("approximate")
            for name, spec in parity.COVERED.items()
            if name != "device_rhythm"
        )


class TestScalarBand:
    def test_the_scalar_band_is_half_a_sigma_not_half_a_bit(self):
        from services.service_sa.sa.learners import scalar

        margin = parity.NEAR_BAR_MARGIN_BITS["scalar_baseline"]
        bar = parity.BAR_BITS["scalar_baseline"]

        assert bar == parity._z_bits(scalar.MIN_ABS_Z)
        assert margin == parity._z_bits(scalar.MIN_ABS_Z + 0.5) - bar
        assert margin > 2.0  # the 4 sigma bar is near 14 bits; half a bit would be a sliver

    def test_a_flag_half_a_sigma_over_the_bar_is_borderline_for_scalar_only(self):
        bar = parity.BAR_BITS["scalar_baseline"]
        flagged = {DAYS[1]: {"bits": bar + 2.0, "confidence": 0.5, "n": 1}}

        wide = parity.compare_days(
            flagged, {}, DAYS, bar, parity.NEAR_BAR_MARGIN_BITS["scalar_baseline"]
        )
        narrow = parity.compare_days(flagged, {}, DAYS, bar)

        assert wide["outcomes"]["borderline"] == 1
        assert narrow["outcomes"]["live_only"] == 1
