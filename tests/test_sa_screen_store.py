"""Storing the discovery screen's findings (sa/screen.py store/run) and the nightly stage. The table
is created by migration 0064; the read-only route is tested in test_api_service.py."""

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.service_sa.sa import screen

RUN = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 3, 40)


def _row(target="guests_home", feature="outdoor_temp_c", lag=0, status="effect", **fields):
    row = {
        "run_date": RUN,
        "target_key": target,
        "feature_key": feature,
        "lag_hours": lag,
        "method": "rates",
        "status": status,
        "reason": "beat the shifted-feature null after multiple-testing correction",
        "n": 790,
        "effect": 0.15,
        "effect_unit": "guests_home per hour, top third minus bottom third",
        "improvement": 0.05,
        "p": 0.005,
        "p_adjusted": 0.04,
        "fitted_from": date(2026, 10, 16),
        "fitted_to": date(2026, 11, 18),
        "evidence": {"transform": "anomaly", "seed": 20261118},
        "computed_at": NOW,
    }
    row.update(fields)
    return row


class TestStore:
    def test_a_night_replaces_its_own_rows_and_prunes_old_runs_in_one_transaction(self):
        conn = MagicMock()

        n = screen.store(conn, [_row(), _row(feature="outdoor_humidity_pct", status="not_tested")])

        cursor = conn.cursor.return_value
        assert n == 2
        deletes = [c.args for c in cursor.execute.call_args_list]
        assert deletes[0] == ("DELETE FROM sa_covariate_findings WHERE run_date = %s", (RUN,))
        assert deletes[1][0] == "DELETE FROM sa_covariate_findings WHERE run_date < %s"
        assert deletes[1][1] == (date(2026, 8, 21),)  # 90 days before the run
        sql, rows = cursor.executemany.call_args.args
        assert sql.startswith("INSERT INTO sa_covariate_findings (run_date, target_key")
        assert sql.count("%s") == 17 and len(rows) == 2  # parameterised, never formatted in
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_a_row_carries_its_evidence_as_json_and_its_reason_is_capped(self):
        conn = MagicMock()

        screen.store(conn, [_row(reason="x" * 400)])

        row = conn.cursor.return_value.executemany.call_args.args[1][0]
        assert row[:6] == (RUN, "guests_home", "outdoor_temp_c", 0, "rates", "effect")
        assert len(row[6]) == 255
        assert json.loads(row[15]) == {"transform": "anomaly", "seed": 20261118}
        assert row[16] == NOW

    def test_a_whole_target_row_is_stored_with_no_numbers(self):
        conn = MagicMock()
        blank = dict.fromkeys(("n", "effect", "effect_unit", "improvement", "p", "p_adjusted"))

        screen.store(
            conn,
            [
                _row(
                    feature="*",
                    status="insufficient_evidence",
                    reason="no data",
                    evidence={},
                    **blank
                )
            ],
        )

        row = conn.cursor.return_value.executemany.call_args.args[1][0]
        assert row[2] == "*" and row[5] == "insufficient_evidence"
        assert row[7:13] == (None,) * 6

    def test_a_failure_rolls_back_and_raises(self):
        conn = MagicMock()
        conn.cursor.return_value.executemany.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError):
            screen.store(conn, [_row()])

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_nothing_to_store_touches_nothing(self):
        conn = MagicMock()

        assert screen.store(conn, []) == 0
        conn.cursor.assert_not_called()

    def test_run_screens_the_lake_and_stores_the_rows(self):
        conn = MagicMock()
        rows = [_row(), _row(feature="is_holiday", status="insufficient_evidence")]
        with patch.object(screen, "run_screen", return_value=rows):
            out = screen.run("/lake", conn)

        assert out["rows"] == 2
        assert out["summary"]["guests_home"] == {
            "effect": 1,
            "insufficient_evidence": 1,
            "not_tested": 0,
        }


class TestNightlyStage:
    def test_a_screen_failure_never_stops_the_nightly_job(self):
        from services.service_sa import learner

        with patch.object(learner.inference_store, "connect", side_effect=RuntimeError("no db")):
            learner.run_discovery_screen()  # must not raise

    def test_a_missing_table_is_logged_not_raised(self):
        from services.service_sa import learner

        conn = MagicMock()
        with patch.object(learner.inference_store, "connect", return_value=conn), patch.object(
            learner.screen, "run", side_effect=RuntimeError("Table doesn't exist (migration 0064)")
        ):
            learner.run_discovery_screen()

        conn.close.assert_called_once()

    def test_the_connection_is_always_closed(self):
        from services.service_sa import learner

        conn = MagicMock()
        with patch.object(learner.inference_store, "connect", return_value=conn), patch.object(
            learner.screen, "run", return_value={"rows": 1, "summary": {}}
        ):
            learner.run_discovery_screen()

        conn.close.assert_called_once()

    def test_the_screen_runs_last_after_the_ledger_and_the_learners(self):
        from services.service_sa import learner

        order = []
        with patch.object(learner.lake, "run_export", return_value={"failures": []}), patch.object(
            learner.external, "run_all", return_value={}
        ), patch.object(
            learner.silver, "run_build", side_effect=lambda **k: order.append("silver") or {}
        ), patch.object(
            learner, "run_ledger", side_effect=lambda: order.append("ledger")
        ), patch.object(
            learner, "run_learners", side_effect=lambda: order.append("learners")
        ), patch.object(
            learner, "run_discovery_screen", side_effect=lambda: order.append("screen")
        ):
            learner.run_bronze_export()

        assert order == ["silver", "ledger", "learners", "screen"]
