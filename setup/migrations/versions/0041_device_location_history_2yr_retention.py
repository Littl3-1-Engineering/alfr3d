"""device_location_history retention 180 days -> 730 days (2 years)

Raises this table's retention to match the other SA event-log tables
(household_events/attention_telemetry_history/card_interactions -- see
alfr3ddaemon.SA_EVENT_LOG_RETENTION_DAYS_DEFAULT). See todo/todo_sa_data_retention_3yr.md.

The retention lives in a MySQL-native scheduled EVENT here (migration 036), not a Python-side
constant like its three siblings -- recreating the event is the minimal correct fix for the
number itself. This event is owned by this deployment's own migration user, not
root/SYSTEM_USER, so DROP+CREATE from here is safe -- see run_sql.py's event_exists() docstring.

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-13
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_038_device_location_history_2yr_retention.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_device_location_history_event`;")
    DELIMITER_SQL = """
    CREATE EVENT `cleanup_device_location_history_event`
    ON SCHEDULE EVERY 1 DAY
    DO
       DELETE FROM device_location_history WHERE captured_at < DATE_SUB(NOW(), INTERVAL 180 DAY);
    """
    op.execute(DELIMITER_SQL)
