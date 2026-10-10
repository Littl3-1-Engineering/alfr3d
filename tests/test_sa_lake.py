"""Tests for service_sa/sa/lake.py: the Parquet bronze layer (LF-1b).

MySQL is faked at the two seams the module reads through (_table_columns, _stream_rows) and the
lake is a pytest tmp_path, so nothing here touches a database.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import lake

COLUMNS = [("id", "bigint"), ("occurred_at", "datetime"), ("message", "text"), ("lat", "decimal")]


def _rows(*stamps):
    return [[i, ts, f"m{i}", Decimal("43.5")] for i, ts in enumerate(stamps, start=1)]


def _export(tmp_path, rows, today=date(2026, 10, 9), columns=COLUMNS):
    """Run export_table over `rows`, honouring the `since` filter the way MySQL would."""

    def fake_stream(_conn, _table, _names, _ts_col, since):
        yield from (r for r in rows if r[1] >= since)

    with patch.object(lake, "_table_columns", return_value=columns), patch.object(
        lake, "_stream_rows", side_effect=fake_stream
    ):
        return lake.export_table(MagicMock(), "t", "occurred_at", tmp_path, today=today)


def _partitions(tmp_path, table="t"):
    return {
        p.parent.name: pq.ParquetFile(p).metadata.num_rows
        for p in (tmp_path / "bronze" / table).glob("date=*/part-0.parquet")
    }


class TestArrowTypes:
    def test_maps_every_mysql_type_used_by_the_sa_tables(self):
        import pyarrow as pa

        assert lake.arrow_type("bigint") == pa.int64()
        assert lake.arrow_type("tinyint") == pa.int64()
        assert lake.arrow_type("decimal") == pa.float64()
        assert lake.arrow_type("float") == pa.float64()
        assert lake.arrow_type("datetime") == pa.timestamp("us")
        assert lake.arrow_type("timestamp") == pa.timestamp("us")
        for text_like in ("varchar", "text", "json", "enum", "time"):
            assert lake.arrow_type(text_like) == pa.string()

    def test_unknown_type_fails_loudly_instead_of_guessing(self):
        with pytest.raises(ValueError, match="No Arrow mapping"):
            lake.arrow_type("geometry")


class TestExportTable:
    def test_one_partition_per_utc_day_with_every_row(self, tmp_path):
        rows = _rows(datetime(2026, 10, 7, 1), datetime(2026, 10, 7, 23), datetime(2026, 10, 8, 5))

        result = _export(tmp_path, rows)

        assert _partitions(tmp_path) == {"date=2026-10-07": 2, "date=2026-10-08": 1}
        assert result["rows"] == 3 and result["days"] == 2

    def test_decimals_become_floats_and_values_round_trip(self, tmp_path):
        _export(tmp_path, _rows(datetime(2026, 10, 8, 5)))

        table = pq.read_table(tmp_path / "bronze" / "t" / "date=2026-10-08" / "part-0.parquet")

        assert table.column("lat").to_pylist() == [43.5]
        assert table.column("message").to_pylist() == ["m1"]
        assert table.column("occurred_at").to_pylist() == [datetime(2026, 10, 8, 5)]

    def test_rerun_is_idempotent(self, tmp_path):
        rows = _rows(datetime(2026, 10, 8, 5), datetime(2026, 10, 9, 1))
        _export(tmp_path, rows)
        first = _partitions(tmp_path)

        _export(tmp_path, rows)

        assert _partitions(tmp_path) == first

    def test_rerun_picks_up_rows_added_to_the_last_day(self, tmp_path):
        rows = _rows(datetime(2026, 10, 9, 1))
        _export(tmp_path, rows)
        rows += [[2, datetime(2026, 10, 9, 8), "later", Decimal("1")]]

        _export(tmp_path, rows)

        assert _partitions(tmp_path) == {"date=2026-10-09": 2}

    def test_resumes_from_the_lookback_not_from_the_beginning(self, tmp_path):
        old = datetime(2026, 9, 1, 12)
        _export(tmp_path, _rows(old, datetime(2026, 10, 9, 1)))
        # Make the old day's file recognisable; a resume must not rewrite it.
        marker = tmp_path / "bronze" / "t" / "date=2026-09-01" / "part-0.parquet"
        before = marker.stat().st_mtime_ns

        result = _export(tmp_path, _rows(old, datetime(2026, 10, 9, 1)))

        assert marker.stat().st_mtime_ns == before
        assert result["days"] == 1

    def test_future_dated_partition_does_not_move_the_resume_point_past_today(self, tmp_path):
        # An upcoming calendar event is partitioned under its future date. Resuming from that
        # date would skip events created for the days in between.
        _export(tmp_path, _rows(datetime(2026, 10, 9, 1), datetime(2026, 10, 20, 9)))
        in_between = [[3, datetime(2026, 10, 12, 9), "new", Decimal("1")]]

        _export(tmp_path, _rows(datetime(2026, 10, 9, 1), datetime(2026, 10, 20, 9)) + in_between)

        assert "date=2026-10-12" in _partitions(tmp_path)

    def test_empty_source_writes_nothing(self, tmp_path):
        result = _export(tmp_path, [])

        assert result["rows"] == 0 and _partitions(tmp_path) == {}

    def test_stale_temp_dirs_from_a_crashed_run_are_cleaned_up(self, tmp_path):
        stale = tmp_path / "bronze" / "t" / ".tmp-date=2026-10-08"
        stale.mkdir(parents=True)
        (stale / "part-0.parquet").write_bytes(b"half written")

        _export(tmp_path, _rows(datetime(2026, 10, 8, 5)))

        assert not stale.exists()
        assert _partitions(tmp_path) == {"date=2026-10-08": 1}

    def test_progress_callback_fires_once_per_day_written(self, tmp_path):
        rows = _rows(datetime(2026, 10, 7, 1), datetime(2026, 10, 8, 1))
        progress = MagicMock()

        with patch.object(lake, "_table_columns", return_value=COLUMNS), patch.object(
            lake, "_stream_rows", side_effect=lambda *a: iter(rows)
        ):
            lake.export_table(
                MagicMock(),
                "t",
                "occurred_at",
                tmp_path,
                progress=progress,
                today=date(2026, 10, 9),
            )

        assert progress.call_count == 2


class TestSecrets:
    def test_secret_looking_column_is_refused(self, tmp_path):
        bad = COLUMNS + [("api_token", "varchar")]

        with pytest.raises(ValueError, match="look like secrets"):
            _export(tmp_path, _rows(datetime(2026, 10, 8, 5)), columns=bad)

    def test_every_snapshot_exclusion_is_for_a_real_sensitive_column(self):
        assert "password_hash" in lake.EXCLUDED_COLUMNS["user"]
        assert "email" in lake.EXCLUDED_COLUMNS["user"]
        assert "stream_url" in lake.EXCLUDED_COLUMNS["device"]
        assert "last_state" in lake.EXCLUDED_COLUMNS["smarthome_devices"]
        assert "actions" in lake.EXCLUDED_COLUMNS["routines"]

    def test_snapshot_drops_excluded_columns_and_never_writes_them(self, tmp_path):
        user_cols = [
            ("id", "int"),
            ("username", "varchar"),
            ("password_hash", "varchar"),
            ("email", "varchar"),
        ]
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = [(1, "athos", "$2b$secret", "a@b.c")]

        with patch.object(lake, "_table_columns", return_value=user_cols):
            lake.export_snapshot(conn, "user", tmp_path, today=date(2026, 10, 9))

        file = tmp_path / "bronze" / "_snapshots" / "user" / "date=2026-10-09" / "part-0.parquet"
        table = pq.read_table(file)
        assert table.column_names == ["id", "username"]
        assert b"secret" not in file.read_bytes()
        sql = conn.cursor.return_value.execute.call_args.args[0]
        assert "password_hash" not in sql and "email" not in sql

    def test_snapshot_of_an_empty_table_writes_no_file(self, tmp_path):
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = []

        with patch.object(lake, "_table_columns", return_value=[("id", "int")]):
            lake.export_snapshot(conn, "states", tmp_path, today=date(2026, 10, 9))

        assert not list((tmp_path / "bronze" / "_snapshots" / "states").glob("date=*"))


class TestRunExport:
    def test_one_failing_table_does_not_stop_the_rest(self, tmp_path):
        calls = []

        def fake_export(_conn, table, _ts, *_a, **_k):
            calls.append(table)
            if table == "household_events":
                raise RuntimeError("boom")
            return {"table": table, "rows": 0, "days": 0, "since": None}

        with patch.object(lake, "_connect", return_value=MagicMock()), patch.object(
            lake, "export_table", side_effect=fake_export
        ), patch.object(lake, "export_snapshot"), patch.object(lake, "record_lake_sizes"):
            outcome = lake.run_export(lake_dir=str(tmp_path))

        assert outcome["failures"] == ["household_events"]
        assert calls == [t for t, _ in lake.EVENT_TABLES]

    def test_second_concurrent_export_is_refused(self, tmp_path):
        with lake._ExportLock(str(tmp_path)):
            with pytest.raises(RuntimeError, match="already running"):
                with lake._ExportLock(str(tmp_path)):
                    pass

    def test_lock_is_released_so_the_next_export_can_run(self, tmp_path):
        with lake._ExportLock(str(tmp_path)):
            pass
        with lake._ExportLock(str(tmp_path)):
            pass


class TestLakeSizes:
    def test_partition_stats_reads_row_counts_from_parquet_footers(self, tmp_path):
        _export(tmp_path, _rows(datetime(2026, 10, 7, 1), datetime(2026, 10, 8, 1)))

        stats = lake.partition_stats(tmp_path)

        assert stats["t"]["rows"] == 2 and stats["t"]["days"] == 2 and stats["t"]["bytes"] > 0

    def test_sizes_are_recorded_in_sa_storage_metrics_with_a_lake_prefix(self, tmp_path):
        _export(tmp_path, _rows(datetime(2026, 10, 8, 1)))
        conn = MagicMock()

        lake.record_lake_sizes(conn, tmp_path)

        sql, args = conn.cursor.return_value.execute.call_args.args
        assert "sa_storage_metrics" in sql
        assert args[0] == "lake.t" and args[1] == 1 and args[2] > 0
        conn.commit.assert_called_once()
