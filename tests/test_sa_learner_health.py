"""Tests for the stale-fit alert: common/learner_health.py (pure), the nightly job's per-learner
outcomes and events (service_sa/learner.py), and the read-only /api/health block.

The trap these pin: drift.apply_stability re-stamps `computed_at` on profiles it caps, so freshness
must come from `fitted_to` (a real fit's data horizon), never from `computed_at`.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from common import learner_health as lh

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def _row(learner, fitted_to, computed_at=None):
    return (learner, fitted_to, computed_at or datetime(2026, 11, 19, 3, 30))


class TestStaleFits:
    def test_a_healthy_nightly_fit_is_not_stale(self):
        # fitted 03:30 today on data through yesterday: one day behind
        assert lh.stale_fits([_row("scalar_baseline", date(2026, 11, 18))], NOW) == []

    def test_the_hours_just_before_the_next_run_are_still_healthy(self):
        # at 03:29 the next morning the same fit reads two days behind
        late = datetime(2026, 11, 20, 3, 29, tzinfo=timezone.utc)

        assert lh.stale_fits([_row("scalar_baseline", date(2026, 11, 18))], late) == []

    def test_one_missed_night_is_flagged_from_midnight_about_twenty_hours_later(self):
        # the 03:30 fit on 11-19 failed: fitted_to is still 11-17
        stale_fit = [_row("scalar_baseline", date(2026, 11, 17))]
        noon = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        midnight = datetime(2026, 11, 20, 0, 5, tzinfo=timezone.utc)

        assert lh.stale_fits(stale_fit, noon) == []  # two days behind is still within normal
        flagged = lh.stale_fits(stale_fit, midnight)
        assert [(s["learner"], s["days_behind"]) for s in flagged] == [("scalar_baseline", 3)]

    def test_a_drift_restamped_computed_at_does_not_hide_a_failed_fit(self):
        """The trap: drift rewrote computed_at to this morning, but fitted_to is a week old."""
        fresh_stamp = datetime(2026, 11, 19, 3, 31)

        out = lh.stale_fits([("stay_profile", date(2026, 11, 12), fresh_stamp)], NOW)

        assert [s["learner"] for s in out] == ["stay_profile"]
        assert out[0]["days_behind"] == 7

    def test_presence_bridge_has_no_fitted_to_and_falls_back_to_computed_at(self):
        ok = ("presence_bridge", None, datetime(2026, 11, 19, 3, 30))
        old = ("presence_bridge", None, datetime(2026, 11, 14, 3, 30))

        assert lh.stale_fits([ok], NOW) == []
        assert lh.stale_fits([old], NOW)[0]["days_behind"] == 5

    def test_a_learner_that_has_never_fitted_is_reported_not_ignored(self):
        out = lh.stale_fits([("brand_new", None, None)], NOW)

        assert out == [{"learner": "brand_new", "fitted_to": None, "days_behind": None}]

    def test_the_worst_learner_comes_first(self):
        rows = [
            _row("a", date(2026, 11, 14)),
            _row("b", date(2026, 11, 10)),
            ("c", None, None),
        ]

        assert [s["learner"] for s in lh.stale_fits(rows, NOW)] == ["c", "b", "a"]

    def test_summarize_is_ok_when_nothing_is_stale_and_names_the_stale_ones_otherwise(self):
        ok = lh.summarize([_row("a", date(2026, 11, 18))], NOW)
        bad = lh.summarize([_row("a", date(2026, 11, 18)), _row("b", date(2026, 11, 10))], NOW)

        assert ok["status"] == "ok" and ok["stale"] == [] and ok["learners"] == 1
        assert bad["status"] == "stale" and [s["learner"] for s in bad["stale"]] == ["b"]


class TestFitEvents:
    def test_a_clean_night_is_one_summary_event_not_nine(self):
        outcomes = {f"l{i}": ("fit_ok", {}) for i in range(9)}

        events = lh.fit_events(outcomes, NOW)

        assert len(events) == 1
        assert events[0]["verb"] == "fit_ok" and events[0]["type"] == "info"
        assert events[0]["message"] == "9 of 9 learners fitted"

    def test_a_failure_gets_its_own_warning_and_the_summary_turns_partial(self):
        outcomes = {"a": ("fit_ok", {}), "stay_profile": ("fit_failed", "boom" * 100)}

        events = lh.fit_events(outcomes, NOW)

        failed = next(e for e in events if e["verb"] == "fit_failed")
        summary = next(e for e in events if e["subject_id"] == "all")
        assert failed["subject_id"] == "stay_profile" and failed["type"] == "warning"
        assert len(failed["message"]) < 260  # an exception text never floods the log
        assert summary["verb"] == "fit_partial" and "stay_profile" in summary["message"]

    def test_events_have_the_shape_the_api_persists(self):
        event = lh.fit_events({"a": ("fit_ok", {})}, NOW)[0]

        assert {"id", "type", "message", "time", "subject_type", "subject_id", "verb"} <= set(event)
        assert event["service"] == "sa-learner" and event["subject_type"] == "learner"


class TestNightlyJob:
    def test_every_learner_runs_even_when_one_raises_and_the_outcomes_are_recorded(self):
        from services.service_sa import learner

        conn = MagicMock()
        stages = [
            (name, label, MagicMock(run_fit=MagicMock(return_value={"profiles": 1})))
            for name, label, _m in learner.LEARNER_STAGES
        ]
        stages[3][2].run_fit.side_effect = RuntimeError("boom")
        with patch.object(learner, "LEARNER_STAGES", tuple(stages)), patch.object(
            learner.inference_store, "connect", return_value=conn
        ), patch.object(learner, "publish_fit_events") as publish:
            outcomes = learner.run_learners()

        assert all(m.run_fit.called for _n, _l, m in stages)  # one failure stops nobody
        assert outcomes[stages[3][0]][0] == "fit_failed"
        assert sum(1 for v in outcomes.values() if v[0] == "fit_ok") == len(stages) - 1
        publish.assert_called_once_with(outcomes)
        conn.close.assert_called_once()

    def test_the_stages_cover_every_learner_that_writes_profiles_in_order(self):
        from services.service_sa import learner

        names = [n for n, _l, _m in learner.LEARNER_STAGES]

        assert names[0] == "presence_bridge" and names[-1] == "drift"  # drift caps what ran before
        assert len(set(names)) == len(names) == 9

    def test_publishing_never_raises_even_when_kafka_is_down(self):
        from services.service_sa import learner

        with patch.object(learner, "get_producer", side_effect=RuntimeError("no kafka")):
            learner.publish_fit_events({"a": ("fit_ok", {})})  # must not raise

    def test_published_events_go_to_the_event_stream(self):
        from services.service_sa import learner

        producer = MagicMock()
        with patch.object(learner, "get_producer", return_value=producer):
            learner.publish_fit_events({"a": ("fit_failed", "boom")})

        topics = {call.args[0] for call in producer.send.call_args_list}
        assert topics == {"event-stream"} and producer.send.call_count == 2
        producer.flush.assert_called_once()
