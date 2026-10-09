"""SA retention gaps: 730 days for device_history, calendar, listening, weather history

LF-0 of the SA learning foundation (todo/sa/todo_lf0_retention_gaps.md). Migration 039/0042
moved four event-log tables to 730 days; this closes the rest: device_history partitions keep
730 days (was 180), calendar_events keeps past events 730 days (was 24 h), listening_history gets
a 730-day cap (was unbounded), weather gets a new environment_history table, and the never-written
device_command_history table is dropped. See migration_043's own comment.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-09
"""

import logging

from alembic import op
from sqlalchemy.exc import OperationalError

from run_sql import event_exists, run_sql_file, sql_path, storage_metrics_proc_sql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_043_sa_retention_gaps.sql")

# MySQL 8 error 1227: dropping an event whose DEFINER holds SYSTEM_USER (e.g. root) needs
# SYSTEM_USER too. Same case 0027 handled for cleanup_device_history_event.
_SYSTEM_USER_REQUIRED = "1227"

# Legacy events this migration must replace or remove. Unlike 0027, leaving them is not
# harmless: cleanup_device_history_event and cleanup_calendar_events_event would keep deleting
# rows older than 180 days / 24 hours and silently defeat the new 730-day windows.
_LEGACY_EVENTS = (
    "cleanup_device_history_event",
    "cleanup_calendar_events_event",
    "cleanup_device_command_history_event",
)


def _drop_legacy_events():
    """Drop the legacy events before changing anything else, so a privilege failure leaves the
    schema untouched and the migration can simply be re-run after the root fix."""
    blocked = []
    for event in _LEGACY_EVENTS:
        if not event_exists(op, event):
            continue
        try:
            op.execute(f"DROP EVENT `{event}`;")
        except OperationalError as exc:
            if _SYSTEM_USER_REQUIRED not in str(exc):
                raise
            blocked.append(event)
    if blocked:
        raise RuntimeError(
            f"Can't drop root-owned event(s) {', '.join(blocked)}: the migration account lacks "
            "SYSTEM_USER. Nothing was changed. Run setup/drop_root_owned_events.sql as root, "
            "then re-run this migration:\n"
            "  docker compose exec -T mysql sh -c "
            '\'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"\' '
            "< setup/drop_root_owned_events.sql"
        )


def upgrade():
    _drop_legacy_events()
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `maintain_device_history_partitions_event`;")
    op.execute(
        "CREATE EVENT `maintain_device_history_partitions_event` ON SCHEDULE EVERY 1 DAY "
        "DO CALL maintain_device_history_partitions(180, 3);"
    )
    op.execute("DROP EVENT IF EXISTS `cleanup_calendar_events_event`;")
    op.execute(
        "CREATE EVENT `cleanup_calendar_events_event` ON SCHEDULE EVERY 1 DAY "
        "DO DELETE FROM calendar_events WHERE end_time < DATE_SUB(NOW(), INTERVAL 24 HOUR);"
    )
    op.execute("DROP EVENT IF EXISTS `cleanup_listening_history_event`;")
    op.execute("DROP EVENT IF EXISTS `cleanup_environment_history_event`;")
    op.execute("DROP TABLE IF EXISTS `environment_history`;")
    # device_command_history comes back empty with its original shape (migration_002_iot.sql);
    # cleanup_device_history_event is not recreated -- 0027 already made the partition event
    # the device_history retention mechanism.
    op.execute(
        "CREATE TABLE IF NOT EXISTS `device_command_history` ("
        "`id` INT NOT NULL AUTO_INCREMENT UNIQUE, "
        "`smarthome_device_id` INT NOT NULL, "
        "`command` VARCHAR(64) NOT NULL, "
        "`params` JSON NULL, "
        "`result` VARCHAR(64) NULL, "
        "`timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (`id`), "
        "FOREIGN KEY (`smarthome_device_id`) REFERENCES `smarthome_devices` (`id`));"
    )
    op.execute(
        "CREATE EVENT `cleanup_device_command_history_event` ON SCHEDULE EVERY 1 DAY "
        "DO DELETE FROM device_command_history "
        "WHERE timestamp < DATE_SUB(NOW(), INTERVAL 180 DAY);"
    )
    # Restore the storage-metrics procedure to its pre-0048 table list (migration_040). Built
    # inline: re-running migration_040's file would fail on its plain CREATE TABLE.
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    op.execute(storage_metrics_proc_sql(_PRE_0048_METRICS_TABLES))


_PRE_0048_METRICS_TABLES = (
    "household_events",
    "card_interactions",
    "attention_telemetry_history",
    "device_location_history",
    "entity_baselines",
    "device_history",
    "smarthome_sensor_history",
)
