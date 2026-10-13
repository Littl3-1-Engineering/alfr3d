"""sa/disk.py (assess tiers, trend, debounce) and SAEngine.check_disk_health."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.service_sa.sa import disk

GB = 1024**3
T0 = datetime(2026, 10, 1)


def _samples(frees, total=100 * GB, step_hours=24):
    return [(T0 + timedelta(hours=step_hours * i), total, int(f * GB)) for i, f in enumerate(frees)]


class TestDaysUntilFull:
    def test_thin_history_gives_no_estimate(self):
        assert disk.days_until_full(_samples([50, 49, 48])) is None

    def test_short_span_gives_no_estimate(self):
        assert disk.days_until_full(_samples([50, 49, 48, 47, 46, 45], step_hours=4)) is None

    def test_linear_growth(self):
        days = disk.days_until_full(_samples([50, 49, 48, 47, 46, 45, 44]))
        assert days == pytest.approx(44, rel=0.01)

    def test_flat_or_shrinking_usage_gives_none(self):
        assert disk.days_until_full(_samples([40] * 8)) is None
        assert disk.days_until_full(_samples([40, 41, 42, 43, 44, 45, 46])) is None


class TestAssess:
    def test_no_data(self):
        assert disk.assess([], []) is None

    def test_healthy_disk_is_ok(self):
        assert disk.assess(_samples([60, 60]), [])["level"] == "ok"

    def test_warn_below_twenty_percent(self):
        assert disk.assess(_samples([19, 19]), [])["level"] == "warn"

    def test_critical_below_ten_percent(self):
        assert disk.assess(_samples([9, 9]), [])["level"] == "critical"

    def test_critical_absolute_floor_on_a_big_disk(self):
        big = _samples([6, 6], total=1000 * GB)
        assert disk.assess(big, [])["level"] == "critical"

    def test_single_odd_reading_does_not_raise_the_level(self):
        assert disk.assess(_samples([60, 5]), [])["level"] == "ok"
        assert disk.assess(_samples([9, 19]), [])["level"] == "warn"

    def test_single_sample_never_alerts(self):
        assert disk.assess(_samples([2]), [])["level"] == "ok"

    def test_days_left_tiers(self):
        # 60 GB free of 100, losing 3 GB/day: ~17 days left -> warn (< 60), not critical (> 14).
        frees = [100 - 3 * i for i in range(8)]
        frees = [f - 10 for f in frees][:8]  # 90..69
        result = disk.assess(_samples(frees), [])
        assert result["days_left"] == pytest.approx(69 / 3, rel=0.02)
        assert result["level"] == "warn"

    def test_lake_over_quarter_of_free_space_warns(self):
        lake = [(T0.date(), 20 * GB)]
        result = disk.assess(_samples([60, 60]), lake)
        assert result["level"] == "warn" and result["lake_flag"] == "large"


class TestLakeRunaway:
    @staticmethod
    def _lake(weekly, recent_week):
        day0 = T0.date()
        series = [(day0 + timedelta(days=i), weekly * i // 7) for i in range(21)]
        last = series[-1][1]
        series.extend(
            (day0 + timedelta(days=21 + i), last + recent_week * (i + 1) // 7) for i in range(7)
        )
        return series

    def test_steady_growth_is_fine(self):
        assert not disk.lake_runaway(self._lake(100 * 1024**2, 100 * 1024**2))

    def test_sudden_jump_is_flagged(self):
        assert disk.lake_runaway(self._lake(20 * 1024**2, 2 * GB))

    def test_tiny_absolute_growth_is_ignored(self):
        assert not disk.lake_runaway(self._lake(1024, 100 * 1024**2))

    def test_thin_history_is_ignored(self):
        assert not disk.lake_runaway([(T0.date(), 1), (T0.date() + timedelta(days=1), 10**12)])


class TestRecordSample:
    def test_inserts_disk_root_row(self, tmp_path):
        conn = MagicMock()
        total, free = disk.record_disk_sample(conn, tmp_path)
        args = conn.cursor().execute.call_args[0]
        assert args[1] == ("disk.root", total, free)
        conn.commit.assert_called_once()


class TestCheckDiskHealth:
    @pytest.fixture(autouse=True)
    def _fresh_state(self):
        from services.service_sa.sa import engine

        engine.DISK_HEALTH_STATE.update({"checked": 0.0, "result": None, "spoke": 0.0})
        yield

    @staticmethod
    def _run(level, now=1_000_000.0, days_left=None):
        from services.service_sa.sa.engine import SAEngine

        result = {
            "level": level,
            "free": 6 * GB,
            "total": 100 * GB,
            "days_left": days_left,
            "lake_bytes": 0,
            "because": ["6.0 GB free of 100.0 GB (6%)"],
        }
        producer = MagicMock()
        with patch("services.service_sa.sa.engine.pymysql.connect"), patch(
            "services.service_sa.sa.engine.disk.load_samples", return_value=[]
        ), patch("services.service_sa.sa.engine.disk.load_lake_totals", return_value=[]), patch(
            "services.service_sa.sa.engine.disk.assess", return_value=result
        ), patch(
            "services.service_sa.sa.engine.get_producer", return_value=producer
        ), patch(
            "services.service_sa.sa.engine.time.time", return_value=now
        ):
            return SAEngine().check_disk_health(None), producer

    def test_ok_gives_no_card(self):
        card, _ = self._run("ok")
        assert card is None

    def test_warn_is_ambient_and_silent(self):
        card, producer = self._run("warn")
        assert card["mode"] == "disk_health" and "urgent" not in card
        producer.send.assert_not_called()

    def test_critical_is_urgent_and_speaks_once_a_day(self):
        card, producer = self._run("critical", days_left=10)
        assert card["urgent"] is True and card["priority"] == 2.1
        assert "full in about 10 days" in card["content"]
        producer.send.assert_called_once()
        assert isinstance(producer.send.call_args[0][1], bytes)
        _, again = self._run("critical", now=1_000_000.0 + 3600)
        again.send.assert_not_called()

    def test_db_error_keeps_the_last_result(self):
        from services.service_sa.sa import engine
        from services.service_sa.sa.engine import SAEngine

        self._run("warn")
        with patch(
            "services.service_sa.sa.engine.pymysql.connect", side_effect=RuntimeError("down")
        ), patch("services.service_sa.sa.engine.time.time", return_value=2_000_000.0):
            card = SAEngine().check_disk_health(None)
        assert card["mode"] == "disk_health"
        assert engine.DISK_HEALTH_STATE["result"]["level"] == "warn"
