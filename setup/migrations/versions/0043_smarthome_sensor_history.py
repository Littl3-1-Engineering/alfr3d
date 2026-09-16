"""SA-9 Phase 2: smarthome_sensor_history table

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-16
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_040_smarthome_sensor_history.sql")


def upgrade():
    if table_exists(op, "smarthome_sensor_history"):
        logger.info("smarthome_sensor_history already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_smarthome_sensor_history_event`;")
    op.execute("DROP TABLE IF EXISTS `smarthome_sensor_history`;")
