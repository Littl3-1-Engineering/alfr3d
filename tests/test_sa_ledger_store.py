"""Tests for storing the capture ledger (sa/ledger.py store/run) and the nightly hook. The table is
created by migration 0063; the read-only route is tested in test_api_service.py."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.service_sa.sa import ledger

LEDGER = {
    "horizon": "2026-11-18T04:00:00",
    "window_days": 30,
    "features": [
        {
            "kind": "feature",
            "key": "outdoor_temp_c",
            "status": "captured",
            "capture_start": "2026-10-09T20:00:00",
            "last_seen": "2026-11-18T03:00:00",
            "rows": 944,
            "hours_with_data_30d": 720,
            "coverage_30d": 0.999,
            "retention_days": 730,
            "privacy": "household",
            "readers": ["scalar_baseline"],
            "provenance": "environment_history",
            "note": "",
        },
        {
            "kind": "feature",
            "key": "precise_location",
            "status": "restricted",
            "capture_start": None,
            "last_seen": None,
            "rows": 0,
            "hours_with_data_30d": 0,
            "coverage_30d": 0.0,
            "retention_days": None,
            "privacy": "restricted",
            "readers": [],
            "provenance": "not captured",
            "note": "never built",
        },
    ],
    "series": [
        {
            "kind": "series",
            "key": "esphome:node.local:Temperature",
            "status": "captured",
            "capture_start": "2026-09-16T15:00:00",
            "last_seen": "2026-11-18T04:00:00",
            "rows": 1000,
            "hours_with_data_30d": 700,
            "coverage_30d": 0.972,
            "retention_days": 730,
            "privacy": "household",
            "readers": ["scalar_baseline", "drift"],
            "provenance": "ESPHome",
            "identity": "host:name, never a row id",
            "note": "",
        }
    ],
    "unregistered": [],
}


class TestStore:
    def test_the_table_is_replaced_in_one_transaction(self):
        conn = MagicMock()

        n = ledger.store(conn, LEDGER, computed_at=datetime(2026, 11, 19, 3, 31))

        cursor = conn.cursor.return_value
        assert n == 3
        assert cursor.execute.call_args.args[0] == "DELETE FROM sa_context_ledger"
        insert_sql, rows = cursor.executemany.call_args.args
        assert insert_sql.startswith("INSERT INTO sa_context_ledger (ledger_key, kind, status")
        assert insert_sql.count("%s") == 17 and len(rows) == 3  # parameterised, never formatted in
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_a_row_carries_the_window_the_horizon_and_json_readers(self):
        conn = MagicMock()

        ledger.store(conn, LEDGER, computed_at=datetime(2026, 11, 19, 3, 31))

        row = conn.cursor.return_value.executemany.call_args.args[1][2]  # the series
        assert row[0] == "esphome:node.local:Temperature" and row[1] == "series"
        assert row[6] == 700 and row[7] == 0.972 and row[8] == 30  # hours, coverage, window
        assert json.loads(row[11]) == ["scalar_baseline", "drift"]
        assert row[13] == "host:name, never a row id"  # identity rule
        assert row[15] == "2026-11-18T04:00:00" and row[16] == datetime(2026, 11, 19, 3, 31)

    def test_a_restricted_feature_is_stored_as_restricted_with_no_capture(self):
        conn = MagicMock()

        ledger.store(conn, LEDGER)

        row = conn.cursor.return_value.executemany.call_args.args[1][1]
        assert row[0] == "precise_location" and row[2] == "restricted"
        assert row[3] is None and row[5] == 0

    def test_a_failure_rolls_back_and_raises(self):
        conn = MagicMock()
        conn.cursor.return_value.executemany.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError):
            ledger.store(conn, LEDGER)

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_an_empty_ledger_clears_the_table_and_inserts_nothing(self):
        conn = MagicMock()
        empty = dict(LEDGER, features=[], series=[])

        assert ledger.store(conn, empty) == 0
        conn.cursor.return_value.executemany.assert_not_called()
        conn.commit.assert_called_once()

    def test_run_builds_from_the_lake_and_reports_unregistered_series(self):
        conn = MagicMock()
        with patch.object(ledger, "build", return_value=dict(LEDGER, unregistered=["mystery:x"])):
            out = ledger.run("/lake", conn)

        assert out == {"rows": 3, "unregistered": ["mystery:x"]}


class TestNightlyHook:
    def test_a_ledger_failure_never_stops_the_nightly_job(self):
        from services.service_sa import learner

        with patch.object(learner.inference_store, "connect", side_effect=RuntimeError("no db")):
            learner.run_ledger()  # must not raise

    def test_the_ledger_runs_after_silver_and_before_the_learners(self):
        from services.service_sa import learner

        order = []
        with patch.object(
            learner.lake,
            "run_export",
            side_effect=lambda **k: order.append("mysql") or {"failures": []},
        ), patch.object(
            learner.external, "run_all", side_effect=lambda **k: order.append("external") or {}
        ), patch.object(
            learner.silver, "run_build", side_effect=lambda **k: order.append("silver") or {}
        ), patch.object(
            learner, "run_ledger", side_effect=lambda: order.append("ledger")
        ), patch.object(
            learner, "run_learners", side_effect=lambda: order.append("learners")
        ):
            learner.run_bronze_export()

        assert order == ["mysql", "external", "silver", "ledger", "learners"]

    def test_the_connection_is_always_closed(self):
        from services.service_sa import learner

        conn = MagicMock()
        with patch.object(learner.inference_store, "connect", return_value=conn), patch.object(
            learner.ledger, "run", return_value={"rows": 1, "unregistered": []}
        ):
            learner.run_ledger()

        conn.close.assert_called_once()
