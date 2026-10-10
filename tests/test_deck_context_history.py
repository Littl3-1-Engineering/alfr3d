# flake8: noqa: F811
"""Tests for the Deck context history writer (routes/context.py, migration 047): change-only
rows, 5 % battery buckets, a heartbeat when nothing changes, the tri-state, and that history can
never fail a report."""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))
# Importing the API test module sets the environment the service needs and provides its fixtures.
from test_api_service import _bearer, api_app, api_client  # noqa: E402,F401

from routes import context  # noqa: E402

DEV = "11111111-1111-4111-8111-111111111111"
T0 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Just enough of a cursor: remembers inserted rows and answers the 'last row' SELECT."""

    def __init__(self):
        self.rows = []  # (observed_at, state tuple)
        self.inserts = []

    def execute(self, sql, params=None):
        if sql.startswith("SELECT observed_at"):
            source, device = params
            matches = [r for r in self.rows if r[0] == source and r[1] == device]
            self._last = (matches[-1][2], *matches[-1][3]) if matches else None
        elif sql.startswith("INSERT INTO deck_context_history"):
            source, device, observed = params[:3]
            state = params[3 : 3 + len(context._DECK_STATE_COLUMNS)]
            self.rows.append((source, device, observed, tuple(state)))
            self.inserts.append(params)

    def fetchone(self):
        return self._last


def _facets(**kw):
    return context._deck_row_from_facets(kw)


class TestFlatten:
    def test_battery_is_bucketed_to_five_percent(self):
        assert _facets(power={"battery_percent": 63})["battery_bucket"] == 60
        assert _facets(power={"battery_percent": 64.9})["battery_bucket"] == 60
        assert _facets(power={"battery_percent": 100})["battery_bucket"] == 100
        assert _facets(power={"battery_percent": -3})["battery_bucket"] == 0

    def test_missing_facets_stay_null_not_false(self):
        row = _facets(interruption={"headset_connected": False})
        assert row["headset_connected"] == 0 and row["dnd_active"] is None
        assert row["is_charging"] is None and row["relay_enabled"] is None

    def test_a_bool_battery_value_is_not_a_percentage(self):
        assert _facets(power={"battery_percent": True})["battery_bucket"] is None

    def test_text_is_truncated_to_the_column_width(self):
        row = _facets(activity={"top_app": "x" * 500})
        assert len(row["top_app"]) == 128


class TestRecord:
    def _state(self, battery=63, dnd=False):
        return _facets(power={"battery_percent": battery}, interruption={"dnd_active": dnd})

    def test_first_report_is_recorded(self):
        cur = FakeCursor()
        assert (
            context._record_deck_context(cur, "device_snapshot", DEV, self._state(), T0)
            == "changed"
        )

    def test_an_unchanged_report_inside_the_heartbeat_window_writes_nothing(self):
        cur = FakeCursor()
        context._record_deck_context(cur, "device_snapshot", DEV, self._state(), T0)
        again = context._record_deck_context(
            cur, "device_snapshot", DEV, self._state(), T0 + timedelta(minutes=5)
        )
        assert again is None and len(cur.inserts) == 1

    def test_a_slow_drain_inside_one_bucket_is_not_a_change(self):
        cur = FakeCursor()
        context._record_deck_context(cur, "device_snapshot", DEV, self._state(63), T0)
        assert (
            context._record_deck_context(
                cur, "device_snapshot", DEV, self._state(61), T0 + timedelta(minutes=1)
            )
            is None
        )
        assert (
            context._record_deck_context(
                cur, "device_snapshot", DEV, self._state(59), T0 + timedelta(minutes=2)
            )
            == "changed"
        )

    def test_dnd_flip_is_a_change(self):
        cur = FakeCursor()
        context._record_deck_context(cur, "device_snapshot", DEV, self._state(dnd=False), T0)
        assert (
            context._record_deck_context(
                cur, "device_snapshot", DEV, self._state(dnd=True), T0 + timedelta(minutes=1)
            )
            == "changed"
        )

    def test_an_unchanged_state_gets_a_heartbeat_after_thirty_minutes(self):
        cur = FakeCursor()
        context._record_deck_context(cur, "device_snapshot", DEV, self._state(), T0)
        kind = context._record_deck_context(
            cur, "device_snapshot", DEV, self._state(), T0 + timedelta(minutes=31)
        )
        assert kind == "heartbeat" and cur.inserts[-1][-1] == 1

    def test_two_decks_and_two_sources_do_not_share_history(self):
        cur = FakeCursor()
        other = "22222222-2222-4222-8222-222222222222"
        assert context._record_deck_context(cur, "device_snapshot", DEV, self._state(), T0)
        assert context._record_deck_context(cur, "device_snapshot", other, self._state(), T0)
        assert context._record_deck_context(
            cur, "surface_state", None, {"active_surface": "music"}, T0
        )
        assert len(cur.inserts) == 3

    def test_a_database_error_is_swallowed(self):
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("table missing")
        assert context._record_deck_context(cur, "device_snapshot", DEV, self._state(), T0) is None


class TestRoutes:
    def _bearer(self):
        return _bearer(2, "resident")

    @patch("routes.context.db_connection")
    def test_device_snapshot_appends_a_history_row(
        self, mock_db_connection, api_client
    ):  # noqa: F811
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_db = MagicMock()
        mock_db.cursor.return_value = cursor
        mock_db_connection.return_value.__enter__.return_value = mock_db

        response = api_client.post(
            "/api/context/device-snapshot",
            json={
                "device_id": DEV,
                "facets": {"power": {"battery_percent": 63, "is_charging": True}},
            },
            headers=self._bearer(),
        )

        assert response.status_code == 200
        inserts = [
            c.args for c in cursor.execute.call_args_list
            if c.args[0].startswith("INSERT INTO deck_context_history")
        ]  # fmt: skip
        assert len(inserts) == 1
        assert inserts[0][1][0] == "device_snapshot" and inserts[0][1][1] == DEV
        assert 60 in inserts[0][1] and 1 in inserts[0][1]

    @patch("routes.context.db_connection")
    def test_history_failure_does_not_fail_the_report(
        self, mock_db_connection, api_client
    ):  # noqa: F811
        cursor = MagicMock()
        cursor.fetchone.return_value = None

        def execute(sql, params=None):
            if "deck_context_history" in sql:
                raise RuntimeError("no such table")

        cursor.execute.side_effect = execute
        mock_db = MagicMock()
        mock_db.cursor.return_value = cursor
        mock_db_connection.return_value.__enter__.return_value = mock_db

        response = api_client.post(
            "/api/context/surface-state",
            json={"active_surface": "music"},
            headers=self._bearer(),
        )

        assert response.status_code == 200
        mock_db.commit.assert_called()
