"""Tests for the LF-3 presence learner: sa/confidence.py, sa/learners/presence.py,
sa/inference_store.py and SAEngine.check_presence_deviation().

The model is exercised on synthetic histories whose answer is known (a person who is home every
weekday 09-17 for weeks, then isn't), so each assertion is about a decision the design made, not a
snapshot of whatever the real data happened to produce.
"""

import math
import re
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import confidence
from services.service_sa.sa import inference_store as store
from services.service_sa.sa.inference_store import (
    delete_profiles_except,
    load_profiles,
    profiles_stamp,
    replace_predictions,
    save_profiles,
    upsert_inference,
)
from services.service_sa.sa.learners import presence
from services.service_sa.sa.learners.base import Inference, Profile

REF = date(2026, 10, 9)  # a Friday


def _history(days, home_when, start=None):
    """Observed grid rows for `days` days ending at REF. home_when(day, hour) -> minutes home."""
    rows = []
    first = start or REF - timedelta(days=days - 1)
    day = first
    while day <= REF:
        for hour in range(24):
            rows.append((day, hour, day.weekday(), home_when(day, hour), True))
        day += timedelta(days=1)
    return rows


def _office_worker_home(day, hour):
    """Home all night; out 09-17 on weekdays; home all weekend."""
    if day.weekday() < 5 and 9 <= hour < 17:
        return 0
    return 60


def _home_worker(day, hour):
    """Home every day, all day: the Athos-before-October pattern."""
    return 60


def _fit(rows, intervals=(), ref=REF, learner=None):
    return (learner or presence.PresenceLearner()).fit_user(1, "athos", rows, list(intervals), ref)


class TestConfidence:
    def test_sufficiency_grows_with_evidence_and_is_zero_with_none(self):
        assert confidence.sufficiency(0) == 0.0
        assert confidence.sufficiency(None) == 0.0
        assert confidence.sufficiency(3.0) == pytest.approx(0.5)
        assert confidence.sufficiency(1) < confidence.sufficiency(5) < confidence.sufficiency(50)
        assert confidence.sufficiency(1000) < 1.0

    def test_value_is_the_product_of_the_four_terms(self):
        c = confidence.Confidence(0.5, 0.8, 0.9, 0.5)

        assert c.value == pytest.approx(0.5 * 0.8 * 0.9 * 0.5)
        assert c.as_dict() == {
            "sufficiency": 0.5,
            "coverage": 0.8,
            "source_quality": 0.9,
            "stability": 0.5,
            "value": 0.18,
        }

    def test_one_collapsed_term_sinks_the_whole_confidence(self):
        assert confidence.Confidence(1, 1, 1, 0).value == 0
        assert confidence.Confidence(1, 0.05, 1, 1).value < 0.06

    def test_a_missing_term_is_refused_not_treated_as_certain(self):
        with pytest.raises(ValueError, match="stability"):
            confidence.Confidence(0.9, 0.9, 0.9, None)

    def test_terms_are_clamped_to_the_unit_interval(self):
        c = confidence.Confidence(5, -1, 1.5, 0.5)

        assert (c.sufficiency, c.coverage, c.source_quality) == (1.0, 0.0, 1.0)


class TestModel:
    def test_a_weekday_habit_is_learned_per_hour(self):
        profile = _fit(_history(60, _office_worker_home))
        cells = presence.cells_from_params(profile.params)

        wednesday = date(2026, 10, 7)
        assert presence.cell(cells, wednesday, 11)[0] < 0.1  # out at 11:00
        assert presence.cell(cells, wednesday, 3)[0] > 0.9  # home at 03:00
        assert presence.cell(cells, date(2026, 10, 10), 11)[0] > 0.9  # home on the weekend

    def test_an_unseen_cell_falls_back_to_its_parent_not_to_zero(self):
        # Only Mondays 10:00 ever observed (as away). Tuesday 10:00 has no data of its own: it
        # must come from the weekday-hour level, which has the Mondays, not default to 0 or 1.
        rows = [(date(2026, 9, 7) + timedelta(days=7 * i), 10, 0, 0, True) for i in range(6)]
        rows += [(date(2026, 9, 8), h, 1, 60, True) for h in range(24) if h != 10] * 4
        cells = presence.fit_cells([(d, h, dw, m) for d, h, dw, m, _ in rows], REF)

        tuesday_10 = cells["p_dow"][1][10]
        monday_10 = cells["p_dow"][0][10]
        assert cells["w_dow"][1][10] == 0
        assert tuesday_10 == pytest.approx(cells["p_dt"]["weekday"][10])
        assert monday_10 < tuesday_10

    def test_recency_weighting_pulls_the_estimate_toward_recent_behaviour(self):
        def moved_out(day, hour):  # home for months, then out 09-17 on weekdays for 3 weeks
            if day >= date(2026, 9, 25) and day.weekday() < 5 and 9 <= hour < 17:
                return 0
            return 60

        rows = [(d, h, dw, m) for d, h, dw, m, _ in _history(120, moved_out)]
        wednesday = date(2026, 10, 7)
        decayed = presence.cell(presence.fit_cells(rows, REF), wednesday, 11)[0]
        with patch.object(presence, "HALF_LIFE_DAYS", 1e9):  # no forgetting at all
            flat = presence.cell(presence.fit_cells(rows, REF), wednesday, 11)[0]
        always_home = presence.cell(
            presence.fit_cells(
                [(d, h, dw, m) for d, h, dw, m, _ in _history(120, _home_worker)], REF
            ),
            wednesday,
            11,
        )[0]

        # With decay the recent absences count for more than they do in a flat average, and both
        # sit well below a person who was never out.
        assert decayed < flat < always_home
        assert always_home - decayed > 0.3

    def test_holidays_do_not_pollute_the_weekday_cells_and_use_the_offday_level(self):
        # Every Thanksgiving (Mon 2026-10-12) style holiday is spent home; ordinary Mondays out.
        def pattern(day, hour):
            if day == date(2026, 9, 7):  # Labour Day, a Monday
                return 60
            if day.weekday() < 5 and 9 <= hour < 17:
                return 0
            return 60

        cells = presence.fit_cells([(d, h, dw, m) for d, h, dw, m, _ in _history(60, pattern)], REF)

        # The holiday's own 60s are not in Monday's cell, so Monday 11:00 is still firmly "out".
        assert cells["p_dow"][0][11] < 0.15
        # And the holiday itself is predicted from the offday level (home).
        assert presence.cell(cells, date(2026, 9, 7), 11)[0] > cells["p_dow"][0][11]

    def test_ontario_holiday_counts_as_an_offday(self):
        assert presence.is_offday(date(2026, 10, 12))  # Thanksgiving Monday
        assert presence.is_offday(date(2026, 10, 10))  # Saturday
        assert not presence.is_offday(date(2026, 10, 9))  # ordinary Friday

    def test_too_little_history_gives_no_profile_at_all(self):
        assert _fit(_history(2, _home_worker)) is None  # 48 hours < MIN_OBSERVED_HOURS

    def test_unobserved_hours_are_not_evidence(self):
        rows = [(d, h, dw, 0, False) for d, h, dw, _m, _ok in _history(60, _home_worker)]

        assert _fit(rows) is None  # every hour was a collector outage: nothing to learn from


class TestProfileTerms:
    def test_coverage_is_the_observed_share_of_the_last_fortnight(self):
        rows = _history(40, _home_worker)
        # Knock out every other hour of the last 14 days.
        cut = REF - timedelta(days=13)
        rows = [(d, h, dw, m, ok and not (d >= cut and h % 2 == 0)) for d, h, dw, m, ok in rows]

        assert presence.coverage_of(rows, REF) == pytest.approx(0.5, abs=0.01)

    def test_source_quality_is_sighting_density_against_a_steady_phone(self):
        start = datetime(2026, 10, 1, 12, 0)
        steady = [(start, start + timedelta(minutes=99), 94)]  # ~0.94/min
        sleepy = [(start, start + timedelta(minutes=99), 30)]  # a phone that naps

        assert presence.source_quality_of(steady, REF) == pytest.approx(1.0)
        assert presence.source_quality_of(sleepy, REF) == pytest.approx(0.33, abs=0.03)
        assert presence.source_quality_of([], REF) == presence.QUALITY_FLOOR
        assert presence.source_quality_of([(start, start, 1)], REF) >= presence.QUALITY_FLOOR

    def test_stability_is_full_when_the_recent_past_was_no_harder_to_predict(self):
        stability, detail = presence.stability_of(
            [(d, h, dw, m) for d, h, dw, m, _ in _history(90, _office_worker_home)], REF
        )

        assert stability == pytest.approx(1.0)
        assert detail["error_recent"] <= detail["error_prior"] + 1e-9

    def test_stability_falls_when_the_pattern_just_changed(self):
        def regime_change(day, hour):
            if day >= REF - timedelta(days=10) and day.weekday() < 5 and 9 <= hour < 17:
                return 0  # suddenly out all day, after months at home
            return 60

        stability, detail = presence.stability_of(
            [(d, h, dw, m) for d, h, dw, m, _ in _history(90, regime_change)], REF
        )

        assert stability < 0.6
        assert detail["error_recent"] > detail["error_prior"]

    def test_stability_is_a_middling_value_not_certainty_when_unmeasurable(self):
        stability, detail = presence.stability_of(
            [(d, h, dw, m) for d, h, dw, m, _ in _history(10, _home_worker)], REF
        )

        assert stability == presence.STABILITY_UNKNOWN < 1.0
        assert "note" in detail

    def test_the_profile_carries_every_confidence_term_and_serialises(self):
        start = datetime(2026, 10, 1, 12, 0)
        profile = _fit(
            _history(60, _office_worker_home), [(start, start + timedelta(minutes=99), 94)]
        )

        assert profile.subject_type == "user" and profile.signal == "presence.home"
        for term in (profile.coverage, profile.source_quality, profile.stability):
            assert 0.0 <= term <= 1.0
        assert len(profile.params["p_dow"]) == 7 and len(profile.params["p_dow"][0]) == 24
        assert profile.fitted_to == REF and profile.params["username"] == "athos"


class TestScoring:
    @pytest.fixture
    def profile(self):
        start = datetime(2026, 10, 1, 12, 0)
        return _fit(_history(60, _home_worker), [(start, start + timedelta(minutes=99), 94)])

    def _score(self, profile, home, away, when=datetime(2026, 10, 9, 11, 30)):
        now_utc = when + timedelta(hours=4)
        state = {"home": home, "away_minutes": away, "local_dt": when}
        return presence.PresenceLearner().score(profile, state, now_utc)

    def test_away_when_always_home_is_a_deviation_with_probability_and_confidence(self, profile):
        inference = self._score(profile, home=False, away=180)

        assert inference.kind == "deviation" and inference.subject_id == "1"
        assert inference.probability < 0.1 and inference.surprise > presence.MIN_SURPRISE_BITS
        assert inference.surprise == pytest.approx(-math.log2(inference.probability), abs=0.01)
        assert 0 < inference.confidence <= 1
        assert inference.observed == {"state": "away", "away_minutes": 180}
        assert inference.context["hour_local"] == 11 and inference.context["dow"] == 4
        # The window starts at the last sighting, not at "now", so a deviation that persists
        # updates one stored row instead of adding one per minute.
        assert inference.window_start == datetime(2026, 10, 9, 15, 30) - timedelta(minutes=180)

    def test_being_home_when_usually_home_is_not_a_deviation(self, profile):
        assert self._score(profile, home=True, away=None) is None

    def test_a_short_absence_is_never_a_deviation(self, profile):
        # Phones nap ~30 min without anyone leaving: under MIN_AWAY_MINUTES proves nothing.
        assert self._score(profile, home=False, away=45) is None
        assert self._score(profile, home=False, away=None) is None
        assert self._score(profile, home=False, away=presence.MIN_AWAY_MINUTES) is not None

    def test_home_when_always_away_is_the_mirror_deviation(self):
        profile = _fit(_history(60, _office_worker_home))

        inference = self._score(profile, home=True, away=None, when=datetime(2026, 10, 7, 11, 30))

        assert inference.observed["state"] == "home" and inference.surprise > 3
        # A "home" deviation has no last-sighting to anchor on: it is keyed to the hour.
        assert inference.window_start.minute == 0

    def test_confidence_reflects_the_profile_terms_and_the_cells_evidence(self, profile):
        profile.coverage, profile.source_quality, profile.stability = 1.0, 1.0, 1.0
        full = self._score(profile, home=False, away=180)
        profile.stability = 0.5
        shaken = self._score(profile, home=False, away=180)

        assert shaken.confidence == pytest.approx(full.confidence * 0.5, rel=0.02)
        assert full.evidence["terms"]["value"] == pytest.approx(full.confidence, abs=0.001)

    def test_a_holiday_is_scored_against_the_offday_pattern(self):
        profile = _fit(_history(60, _office_worker_home))
        thanksgiving = datetime(2026, 10, 12, 11, 30)  # Monday, a holiday

        # Out on a holiday is expected of an office worker who is home on days off.
        inference = self._score(profile, home=False, away=240, when=thanksgiving)

        assert inference is None or inference.context["holiday"] is True
        # ...and the same absence on an ordinary Monday is not surprising either (they're out).
        assert (
            self._score(profile, home=False, away=240, when=datetime(2026, 10, 5, 11, 30)) is None
        )

    def test_prediction_is_a_24_hour_outlook_in_local_time(self, profile):
        prediction = presence.PresenceLearner().predict(
            profile, datetime(2026, 10, 10, 2, 20), "America/Toronto"  # 22:20 EDT Friday
        )

        hours = prediction.expected["hours"]
        assert prediction.kind == "prediction" and len(hours) == 24
        assert hours[0]["hour_local"] == 23 and hours[0]["dow"] == 4  # next whole local hour
        assert hours[1]["hour_local"] == 0 and hours[1]["dow"] == 5  # rolls over to Saturday
        assert prediction.window_start == datetime(2026, 10, 10, 3, 0)  # 23:00 EDT in UTC
        assert prediction.probability == hours[0]["p_home"]

    def test_prediction_for_someone_rarely_home_says_so(self):
        # A visitor: only ever present on Saturday evenings.
        def visitor(day, hour):
            return 60 if day.weekday() == 5 and 18 <= hour < 23 else 0

        profile = _fit(_history(70, visitor))
        prediction = presence.PresenceLearner().predict(
            profile, datetime(2026, 10, 10, 20, 0), "America/Toronto"
        )

        by_hour = {(h["dow"], h["hour_local"]): h["p_home"] for h in prediction.expected["hours"]}
        assert by_hour[(6, 10)] < 0.2  # Sunday 10:00: not expected
        assert prediction.confidence < 0.8


class TestObservedState:
    INTERVALS = [
        (datetime(2026, 10, 9, 12, 0), datetime(2026, 10, 9, 12, 30), 30),
        (datetime(2026, 10, 9, 18, 25), datetime(2026, 10, 9, 21, 40), 100),
    ]

    def test_home_inside_an_interval_and_shortly_after_its_last_sighting(self):
        assert presence.observed_state(self.INTERVALS, datetime(2026, 10, 9, 12, 10)) == (
            True,
            None,
        )
        # The household's user.state only flips offline ~31 min after the last sighting.
        assert presence.observed_state(self.INTERVALS, datetime(2026, 10, 9, 12, 55)) == (
            True,
            None,
        )

    def test_away_with_minutes_since_the_last_sighting(self):
        home, away = presence.observed_state(self.INTERVALS, datetime(2026, 10, 9, 15, 30))

        assert home is False and away == pytest.approx(180)

    def test_before_the_first_ever_sighting_is_away_with_no_duration(self):
        assert presence.observed_state(self.INTERVALS, datetime(2026, 10, 9, 1, 0)) == (False, None)


class TestReplay:
    """The case that started LF-3, end to end on a synthetic lake: someone home every day for
    weeks, then out on a Friday. The model is fitted only on data before that day."""

    @pytest.fixture
    def lake(self, tmp_path):
        absent_day = date(2026, 10, 9)
        rows, intervals = [], []
        day = date(2026, 8, 10)
        while day <= absent_day:
            for hour in range(24):
                away = day == absent_day and 9 <= hour < 15
                rows.append((day, hour, day.weekday(), 0 if away else 60, True))
            day += timedelta(days=1)
        # One presence interval per day, except the absent Friday's morning gap.
        day = date(2026, 8, 10)
        while day <= absent_day:
            utc = datetime.combine(day, datetime.min.time()) + timedelta(hours=4)  # local midnight
            if day == absent_day:
                intervals.append((utc, utc + timedelta(hours=9), 500))  # until 09:00 local
                intervals.append((utc + timedelta(hours=15), utc + timedelta(hours=23), 500))
            else:
                intervals.append((utc, utc + timedelta(hours=23, minutes=50), 1300))
            day += timedelta(days=1)
        grid = [
            {
                "user_id": 1,
                "username": "athos",
                "bucket_utc": datetime.combine(d, datetime.min.time()) + timedelta(hours=h + 4),
                "date_local": d,
                "hour_local": h,
                "dow_local": dw,
                "minutes_home": float(m),
                "observed": ok,
            }
            for d, h, dw, m, ok in rows
        ]
        (tmp_path / "gold" / "presence_grid").mkdir(parents=True)
        pq.write_table(
            pa.Table.from_pylist(grid), tmp_path / "gold" / "presence_grid" / "part-0.parquet"
        )
        (tmp_path / "silver" / "presence_intervals").mkdir(parents=True)
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "user_id": 1,
                        "user_type": "owner",
                        "start_utc": s,
                        "end_utc": e,
                        "sightings": n,
                    }
                    for s, e, n in intervals
                ]
            ),
            tmp_path / "silver" / "presence_intervals" / "part-0.parquet",
        )
        return str(tmp_path)

    def test_the_absent_friday_is_flagged_and_a_normal_friday_is_not(self, lake):
        flagged = presence.replay(lake, 1, datetime(2026, 10, 9, 11, 30))
        normal = presence.replay(lake, 1, datetime(2026, 10, 2, 11, 30))

        assert flagged["observed"]["home"] is False
        assert flagged["cell"]["p_home"] > 0.9
        assert flagged["inference"] is not None
        assert flagged["inference"].surprise > presence.MIN_SURPRISE_BITS
        assert normal["observed"]["home"] is True and normal["inference"] is None

    def test_replay_never_sees_the_day_it_is_asked_about(self, lake):
        replayed = presence.replay(lake, 1, datetime(2026, 10, 9, 11, 30))

        # Fitted through Thursday: the absence it is judging is not in its own training data.
        assert replayed["profile"]["fitted_to"] == date(2026, 10, 8)

    def test_backtest_flags_only_the_absence(self, lake):
        results = presence.backtest(lake, 1, date(2026, 9, 28), date(2026, 10, 9))

        fired = [r for r in results if r["inference"] is not None]
        assert {r["at_local"].date() for r in fired} == {date(2026, 10, 9)}
        assert all(9 <= r["at_local"].hour < 15 or r["at_local"].hour >= 15 for r in fired)

    def test_unknown_user_is_an_error_not_a_silent_none(self, lake):
        with pytest.raises(ValueError, match="no presence data"):
            presence.replay(lake, 99, datetime(2026, 10, 9, 11, 30))


class TestStore:
    def _conn(self, rows=None, one=None):
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = rows or []
        cursor.fetchone.return_value = one
        return conn, cursor

    def test_save_profiles_upserts_json_params_and_commits(self):
        conn, cursor = self._conn()
        profile = Profile(
            "presence_profile", "1", "user", 1, "presence.home", {"m0": 0.5}, 10.0, 0.9, 0.8, 1.0
        )

        assert save_profiles(conn, [profile]) == 1

        sql, args = cursor.execute.call_args.args
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert args[:5] == ("presence_profile", "1", "user", "1", "presence.home")
        assert args[5] == '{"m0":0.5}'
        conn.commit.assert_called_once()

    def test_profiles_stamp_and_load_round_trip(self):
        stamp = datetime(2026, 10, 10, 1, 0)
        conn, _ = self._conn(one=(stamp,))
        assert profiles_stamp(conn, "presence_profile") == stamp

        conn, _ = self._conn(
            rows=[("presence_profile", "1", "user", "1", "presence.home", '{"m0":0.5}',
                   9.0, 0.9, 0.8, 1.0, date(2026, 5, 1), date(2026, 10, 9), stamp)]
        )  # fmt: skip
        (loaded,) = load_profiles(conn, "presence_profile")
        assert loaded.params == {"m0": 0.5} and loaded.subject_id == "1" and loaded.stability == 1.0

    def test_stamp_of_a_learner_with_no_profiles_is_none(self):
        conn, _ = self._conn(one=(None,))

        assert profiles_stamp(conn, "presence_profile") is None

    def test_stale_profiles_are_removed_and_current_ones_kept(self):
        conn, cursor = self._conn(rows=[("1",), ("2",), ("3",)])

        removed = delete_profiles_except(conn, "presence_profile", [1, "3"])

        assert removed == 1
        delete = cursor.execute.call_args_list[-1].args
        assert delete[1] == ("presence_profile", "2")

    def test_upsert_inference_keys_on_the_window_so_a_persisting_deviation_is_one_row(self):
        conn, cursor = self._conn()
        inference = Inference(
            "deviation", "user", 1, "presence.home", "presence_profile", "1",
            datetime(2026, 10, 9, 12, 30), observed={"state": "away"}, probability=0.1,
        )  # fmt: skip

        upsert_inference(conn, inference)

        sql, args = cursor.execute.call_args.args
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert (
            args[1] == "deviation" and args[3] == "1" and args[6] == datetime(2026, 10, 9, 12, 30)
        )
        assert args[8] == '{"state":"away"}'

    def test_a_new_outlook_replaces_the_previous_one(self):
        conn, cursor = self._conn()
        outlook = Inference(
            "prediction",
            "user",
            1,
            "presence.home",
            "presence_profile",
            "1",
            datetime(2026, 10, 10, 3),
        )

        assert replace_predictions(conn, "presence_profile", [outlook]) == 1

        assert "DELETE FROM sa_inferences" in cursor.execute.call_args_list[0].args[0]
        assert "kind = 'prediction'" in cursor.execute.call_args_list[0].args[0]


class TestReservedWords:
    def test_signal_is_quoted_in_every_statement_that_names_it(self):
        """`signal` is a reserved word in MySQL; an unquoted one is a syntax error that only a real
        server reports (found 2026-10-10 against a scratch MySQL, never by the mocked tests)."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        profile = Profile("presence_profile", "1", "user", 1, "presence.home", {})
        inference = Inference(
            "deviation", "user", 1, "presence.home", "presence_profile", "1", datetime(2026, 10, 9)
        )

        save_profiles(conn, [profile])
        load_profiles(conn, "presence_profile")
        upsert_inference(conn, inference)
        store.latest_prediction(conn, "presence_profile", 1)

        for call in cursor.execute.call_args_list:
            sql = call.args[0]
            for match in re.finditer(r"(?<![`\w])signal(?![`\w])", sql):
                raise AssertionError(f"unquoted `signal` in: {sql}")


class TestRunFit:
    def test_fits_stores_prunes_and_replaces_the_outlook(self):
        profile = Profile(
            "presence_profile", "1", "user", 1, "presence.home", {"username": "athos"}
        )
        with patch.object(presence.PresenceLearner, "fit", return_value=[profile]), patch.object(
            presence.PresenceLearner, "predict", return_value="outlook"
        ), patch.object(presence.inference_store, "save_profiles") as save, patch.object(
            presence.inference_store, "delete_profiles_except", return_value=2
        ) as prune, patch.object(
            presence.inference_store, "replace_predictions"
        ) as replace:
            outcome = presence.run_fit("/lake", MagicMock(), now_utc=datetime(2026, 10, 10, 3))

        assert outcome == {"profiles": 1, "removed": 2, "predictions": 1}
        save.assert_called_once()
        assert prune.call_args.args[2] == ["1"]
        assert replace.call_args.args[2] == ["outlook"]

    def test_an_empty_lake_stores_nothing(self):
        with patch.object(presence.PresenceLearner, "fit", return_value=[]), patch.object(
            presence.inference_store, "save_profiles"
        ) as save:
            outcome = presence.run_fit("/lake", MagicMock())

        assert outcome == {"profiles": 0, "removed": 0, "predictions": 0}
        save.assert_not_called()


# --- The rule inside the awareness loop ----------------------------------------------------


def _frame(people, local_dt=datetime(2026, 10, 9, 11, 30), day="Friday"):
    from services.service_sa.sa.context_frame import ContextFrame

    frame = ContextFrame()
    frame.now = local_dt.replace(tzinfo=None) + timedelta(hours=4)
    frame.now = frame.now.replace(tzinfo=__import__("datetime").timezone.utc)
    frame.local_dt = local_dt
    frame.day_mood = {"day_of_week": day}
    frame.person_presence = people
    return frame


def _person(user_id=1, name="athos", user_type="owner", home=False, minutes_ago=180):
    now_utc = datetime(2026, 10, 9, 15, 30)
    return {
        "user_id": user_id,
        "username": name,
        "user_type": user_type,
        "home": home,
        "last_online": now_utc - timedelta(minutes=minutes_ago),
    }


@pytest.fixture
def engine_with_profile():
    from services.service_sa.sa import engine as sa_engine

    start = datetime(2026, 10, 1, 12, 0)
    engine = sa_engine.SAEngine()
    profiles = {
        str(uid): presence.PresenceLearner().fit_user(
            uid, name, _history(60, _home_worker), [(start, start + timedelta(minutes=99), 94)], REF
        )
        for uid, name in ((1, "athos"), (2, "visitor"), (3, "jenna"))
    }
    with patch.object(engine, "_presence_profiles", return_value=profiles), patch.object(
        engine, "_persist_inferences"
    ) as persist, patch.object(engine, "_calendar_busy_at", return_value=False):
        engine.persist = persist
        yield engine


class TestCheckPresenceDeviation:
    def test_an_owner_away_when_usually_home_gets_an_ambient_card(self, engine_with_profile):
        card = engine_with_profile.check_presence_deviation(_frame([_person()]))

        assert card["mode"] == "presence_deviation" and card["entity_name"] == "athos"
        assert "athos is out" in card["content"] and "Fridays" in card["content"]
        assert "?" not in card["content"]  # an observation, never a welfare check
        assert card["data"]["away_minutes"] == 180
        assert card["data"]["surprise_bits"] > 3 and 0 < card["data"]["confidence"] <= 1
        assert len(card["data"]["because"]) == 3
        assert card["priority"] == 2.75

    def test_the_deviation_is_recorded_whether_or_not_a_card_results(self, engine_with_profile):
        guest = _person(user_id=2, name="visitor", user_type="guest")

        card = engine_with_profile.check_presence_deviation(_frame([guest]))

        assert card is None  # a guest leaving isn't a card...
        (recorded,), _ = engine_with_profile.persist.call_args  # ...but it is an inference
        assert len(recorded) == 1 and recorded[0].subject_id == "2"

    def test_someone_who_is_home_produces_nothing(self, engine_with_profile):
        card = engine_with_profile.check_presence_deviation(
            _frame([_person(home=True, minutes_ago=0)])
        )

        assert card is None
        engine_with_profile.persist.assert_not_called()

    def test_a_short_absence_produces_nothing(self, engine_with_profile):
        assert (
            engine_with_profile.check_presence_deviation(_frame([_person(minutes_ago=40)])) is None
        )

    def test_low_confidence_records_the_inference_but_shows_no_card(self, engine_with_profile):
        profile = engine_with_profile._presence_profiles()["1"]
        profile.stability = 0.1  # the model has been badly wrong lately

        card = engine_with_profile.check_presence_deviation(_frame([_person()]))

        assert card is None
        engine_with_profile.persist.assert_called_once()

    def test_a_booked_calendar_event_is_not_a_deviation(self, engine_with_profile):
        with patch.object(engine_with_profile, "_calendar_busy_at", return_value=True):
            card = engine_with_profile.check_presence_deviation(_frame([_person()]))

        assert card is None

    def test_the_most_surprising_person_wins_the_single_card(self, engine_with_profile):
        a = _person(user_id=1, name="athos", minutes_ago=180)
        b = _person(user_id=3, name="jenna", user_type="resident", minutes_ago=180)
        engine_with_profile._presence_profiles()["3"] = presence.PresenceLearner().fit_user(
            3, "jenna", _history(60, _home_worker), [], REF
        )  # no phone sightings: lower source quality -> lower confidence

        card = engine_with_profile.check_presence_deviation(_frame([a, b]))

        assert card["entity_name"] == "athos"

    def test_no_profiles_yet_is_silent_not_an_error(self):
        from services.service_sa.sa import engine as sa_engine

        engine = sa_engine.SAEngine()
        with patch.object(engine, "_presence_profiles", return_value={}):
            assert engine.check_presence_deviation(_frame([_person()])) is None

    def test_a_missing_frame_field_is_silent(self, engine_with_profile):
        assert engine_with_profile.check_presence_deviation(_frame(None)) is None

    def test_people_without_a_profile_are_skipped(self, engine_with_profile):
        stranger = _person(user_id=99, name="stranger")

        assert engine_with_profile.check_presence_deviation(_frame([stranger])) is None

    def test_the_rule_is_registered_and_suppressed_per_person(self):
        from services.service_sa.sa import engine as sa_engine

        assert ("presence_deviation", 2.75, "check_presence_deviation") in (
            sa_engine.SAEngine.DISPLAY_RULES
        )
        extractor = sa_engine.CARD_SUBJECT_KEY_EXTRACTORS["presence_deviation"]
        assert extractor({"entity_name": "athos"}) == "athos"


class TestProfileReload:
    def test_profiles_reload_only_when_a_newer_fit_has_landed(self):
        from services.service_sa.sa import engine as sa_engine

        engine = sa_engine.SAEngine()
        stamp = datetime(2026, 10, 10, 1, 0)
        profile = Profile("presence_profile", "1", "user", 1, "presence.home", {})
        conn = MagicMock()
        with patch.object(sa_engine.pymysql, "connect", return_value=conn), patch.object(
            sa_engine.inference_store, "profiles_stamp", return_value=stamp
        ), patch.object(sa_engine.inference_store, "load_profiles", return_value=[profile]) as load:
            first = engine._presence_profiles()
            second = engine._presence_profiles()

        assert list(first) == ["1"] and first is second
        load.assert_called_once()  # the second cycle saw the same stamp and reused the cache

    def test_a_db_error_keeps_the_last_good_profiles(self):
        from services.service_sa.sa import engine as sa_engine

        engine = sa_engine.SAEngine()
        engine._presence_cache = {"1": "cached"}
        with patch.object(
            sa_engine.pymysql, "connect", side_effect=sa_engine.pymysql.Error("down")
        ):
            assert engine._presence_profiles() == {"1": "cached"}


class TestFetchPersonPresence:
    def test_reads_state_by_phone_and_excludes_the_system_and_catch_all(self):
        from services.service_sa.sa import context_frame

        rows = [
            (1, "athos", "owner", "online", datetime(2026, 10, 10, 2, 18)),
            (9, "Vanja", "resident", "offline", datetime(2026, 9, 3, 13, 25)),
        ]
        with patch.object(context_frame.pymysql, "connect") as connect:
            connect.return_value.cursor.return_value.fetchall.return_value = rows
            people = context_frame.fetch_person_presence()

        sql = connect.return_value.cursor.return_value.execute.call_args.args[0]
        assert "<> 'alfr3d'" in sql and "<> 'unknown'" in sql
        assert people[0] == {
            "user_id": 1, "username": "athos", "user_type": "owner", "home": True,
            "last_online": datetime(2026, 10, 10, 2, 18),
        }  # fmt: skip
        assert people[1]["home"] is False

    def test_a_db_error_is_none_not_an_exception(self):
        from services.service_sa.sa import context_frame

        with patch.object(
            context_frame.pymysql, "connect", side_effect=context_frame.pymysql.Error("x")
        ):
            assert context_frame.fetch_person_presence() is None


class TestLearnerJob:
    def test_run_learners_fits_and_always_closes_the_connection(self):
        from services.service_sa import learner

        conn = MagicMock()
        with patch.object(learner.inference_store, "connect", return_value=conn), patch.object(
            learner.presence, "run_fit", return_value={"profiles": 3}
        ) as fit:
            learner.run_learners()

        fit.assert_called_once()
        conn.close.assert_called_once()

    def test_a_failing_fit_is_logged_and_does_not_escape(self):
        from services.service_sa import learner

        conn = MagicMock()
        with patch.object(learner.inference_store, "connect", return_value=conn), patch.object(
            learner.presence, "run_fit", side_effect=RuntimeError("boom")
        ):
            learner.run_learners()  # must not raise: it runs inside the nightly job

        conn.close.assert_called_once()
