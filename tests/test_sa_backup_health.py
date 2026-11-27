"""Backup freshness: host snapshot parsing, assess_backups tiers and SAEngine.check_backup_health
(todo/todo_db_backup_cron.md, "Still open")."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.service_sa.sa import disk

H = 3600
NOW = 2_000_000_000.0


class TestHostSnapshot:
    def _read(self, tmp_path, line):
        f = tmp_path / "host_usage.tsv"
        f.write_text(f"ts\t1000\nbackups\t3\t100\n{line}")
        return disk.read_host_usage(str(f), now=1001)

    def test_parses_newest_backup(self, tmp_path):
        usage = self._read(tmp_path, "backup_newest\t1999990000\t7\n")
        assert usage["backup_newest"] == (1999990000, 7)

    def test_none_yet_is_ignored(self, tmp_path):
        assert self._read(tmp_path, "backup_newest\t0\t0\n")["backup_newest"] is None

    def test_old_snapshot_without_the_line_still_parses(self, tmp_path):
        assert self._read(tmp_path, "")["backup_newest"] is None

    def test_record_writes_a_row_only_when_present(self, tmp_path):
        f = tmp_path / "h.tsv"
        f.write_text("ts\t1000\nbackup_newest\t1999990000\t7\n")
        conn = MagicMock()
        with patch.object(disk.time, "time", return_value=1001):
            assert disk.record_host_usage(conn, str(f)) == 1
        rows = conn.cursor().executemany.call_args[0][1]
        assert rows == [(disk.BACKUP_NEWEST_TABLE, 1999990000, 7, 0)]


class TestAssessBackups:
    def test_nothing_seen_means_no_judgement(self):
        assert disk.assess_backups(None, NOW) is None

    def test_fresh_is_ok(self):
        assert disk.assess_backups((NOW - 5 * H, 7), NOW)["level"] == "ok"

    def test_a_missed_run_warns(self):
        assert disk.assess_backups((NOW - 37 * H, 7), NOW)["level"] == "warn"

    def test_days_stale_is_critical(self):
        r = disk.assess_backups((NOW - 100 * H, 7), NOW)
        assert r["level"] == "critical" and "100 hours old" in r["because"][0]

    def test_clock_skew_never_goes_negative(self):
        assert disk.assess_backups((NOW + 99 * H, 7), NOW)["age_hours"] == 0

    def test_load_returns_latest_or_none(self):
        conn = MagicMock()
        conn.cursor().fetchone.return_value = (1999990000, 7)
        assert disk.load_backup_newest(conn, datetime(2026, 1, 1)) == (1999990000, 7)
        conn.cursor().fetchone.return_value = None
        assert disk.load_backup_newest(conn, datetime(2026, 1, 1)) is None


class TestCheckBackupHealth:
    @pytest.fixture(autouse=True)
    def _fresh_state(self):
        from services.service_sa.sa import engine

        engine.BACKUP_HEALTH_STATE.update({"checked": 0.0, "newest": None})
        yield

    @staticmethod
    def _run(age_hours, now=NOW):
        from services.service_sa.sa.engine import SAEngine

        newest = None if age_hours is None else (int(now - age_hours * H), 7)
        with patch("services.service_sa.sa.engine.pymysql.connect"), patch(
            "services.service_sa.sa.engine.disk.load_backup_newest", return_value=newest
        ), patch("services.service_sa.sa.engine.time.time", return_value=now):
            return SAEngine().check_backup_health(None)

    def test_fresh_or_unconfigured_gives_no_card(self):
        assert self._run(4) is None
        assert self._run(None) is None

    def test_warn_is_ambient(self):
        card = self._run(40)
        assert card["mode"] == "backup_health" and "urgent" not in card
        assert card["priority"] == 5.85 and "40 hours old" in card["content"]

    def test_critical_is_urgent(self):
        card = self._run(100)
        assert card["urgent"] is True and card["priority"] == 2.15

    def test_db_error_keeps_the_last_reading_and_keeps_aging(self):
        from services.service_sa.sa.engine import SAEngine

        self._run(30)
        later = NOW + 20 * H  # same dump, 50 h old now, DB down
        with patch(
            "services.service_sa.sa.engine.pymysql.connect", side_effect=RuntimeError("down")
        ), patch("services.service_sa.sa.engine.time.time", return_value=later):
            card = SAEngine().check_backup_health(None)
        assert card["mode"] == "backup_health" and "50 hours old" in card["content"]

    def test_registered_in_the_engine_rule_table(self):
        import inspect

        from services.service_sa.sa import engine

        assert '"check_backup_health"' in inspect.getsource(engine)
