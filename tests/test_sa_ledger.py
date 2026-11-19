"""Tests for the capture ledger (sa/ledger.py): it reports what the lake actually holds, flags what
is not captured or restricted, lists series nobody registered, and writes nothing."""

import os
from datetime import datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq

from services.service_sa.sa import context_registry as reg
from services.service_sa.sa import ledger

HORIZON = datetime(2026, 11, 18, 3, 0)


def _write(root, table, rows):
    d = root / "gold" / table
    d.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), d / "part-0.parquet")


def _lake(tmp_path):
    # outdoor_temp_c: hourly for the last 10 days; people_home: sparse; one series per family plus
    # one nobody registered.
    feats = [
        {
            "feature_key": "outdoor_temp_c",
            "bucket_utc": HORIZON - timedelta(hours=i),
            "value_num": 10.0,
            "value_text": None,
        }
        for i in range(240)
    ] + [
        {
            "feature_key": "people_home",
            "bucket_utc": HORIZON - timedelta(hours=i * 24),
            "value_num": 2.0,
            "value_text": None,
        }
        for i in range(20)
    ]
    _write(tmp_path, "context_features", feats)
    series = []
    for key in (
        "esphome:node.local:Temperature",
        "attention:switch_count",
        "mystery:thing",
    ):
        for i in range(48):
            series.append(
                {
                    "series_key": key,
                    "bucket_utc": HORIZON - timedelta(hours=i),
                    "mean": 1.0,
                }
            )
    _write(tmp_path, "scalar_hourly", series)
    return str(tmp_path)


class TestLedger:
    def test_a_captured_feature_reports_its_start_and_its_coverage_of_the_window(self, tmp_path):
        out = ledger.build(_lake(tmp_path), window_days=30)
        entry = next(f for f in out["features"] if f["key"] == "outdoor_temp_c")

        assert entry["status"] == "captured"
        assert entry["capture_start"] == (HORIZON - timedelta(hours=239)).isoformat()
        assert entry["last_seen"] == HORIZON.isoformat()
        assert entry["rows"] == 240
        assert entry["hours_with_data_30d"] == 240
        assert entry["coverage_30d"] == round(240 / 720, 3)

    def test_the_ledger_carries_retention_readers_and_provenance(self, tmp_path):
        out = ledger.build(_lake(tmp_path))
        entry = next(f for f in out["features"] if f["key"] == "outdoor_temp_c")

        assert entry["retention_days"] == 730
        assert "scalar_baseline" in entry["readers"]
        assert "environment_history" in entry["provenance"]

    def test_a_zero_filled_feature_says_so_in_its_note(self, tmp_path):
        out = ledger.build(_lake(tmp_path))
        entry = next(f for f in out["features"] if f["key"] == "calendar_busy_minutes")

        assert "ZERO-FILLED" in entry["note"]

    def test_a_registered_feature_with_no_data_is_listed_as_captured_with_zero_rows(self, tmp_path):
        out = ledger.build(_lake(tmp_path))
        entry = next(f for f in out["features"] if f["key"] == "is_holiday")

        assert (
            entry["rows"] == 0 and entry["coverage_30d"] == 0.0 and entry["capture_start"] is None
        )

    def test_a_restricted_feature_is_listed_as_restricted_never_as_captured(self, tmp_path):
        out = ledger.build(_lake(tmp_path))
        entry = next(f for f in out["features"] if f["key"] == "precise_location")

        assert entry["status"] == "restricted" and entry["rows"] == 0

    def test_a_feature_with_no_source_is_not_captured(self, tmp_path):
        no_source = reg.Feature("planned", "float", None, in_context_hourly=False)

        out = ledger.build(_lake(tmp_path), features=reg.REGISTRY + (no_source,))
        entry = next(f for f in out["features"] if f["key"] == "planned")

        assert entry["status"] == "not_captured"

    def test_series_carry_their_family_identity_and_unregistered_ones_are_flagged(self, tmp_path):
        out = ledger.build(_lake(tmp_path))
        keys = {s["key"]: s for s in out["series"]}

        assert "never a row id" in keys["esphome:node.local:Temperature"]["identity"]
        assert keys["attention:switch_count"]["hours_with_data_30d"] == 48
        assert out["unregistered"] == ["mystery:thing"]  # a new source cannot slip in unseen

    def test_it_is_read_only(self, tmp_path):
        lake = _lake(tmp_path)
        before = sorted(
            (os.path.join(r, f), os.path.getmtime(os.path.join(r, f)))
            for r, _d, files in os.walk(lake)
            for f in files
        )

        ledger.build(lake)

        after = sorted(
            (os.path.join(r, f), os.path.getmtime(os.path.join(r, f)))
            for r, _d, files in os.walk(lake)
            for f in files
        )
        assert before == after

    def test_an_empty_lake_gives_an_empty_ledger_not_an_error(self, tmp_path):
        out = ledger.build(str(tmp_path))

        assert out["horizon"] is None and out["series"] == []
        assert all(f["rows"] == 0 for f in out["features"])
