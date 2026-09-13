"""sa_storage_metrics table

Daily snapshot of row count and on-disk size for the SA-related tables
alfr3ddaemon.SA_STORAGE_METRICS_TRACKED_TABLES names, written by record_sa_storage_metrics().
Turns todo/todo_sa_data_retention_3yr.md's short-window production estimate into a real,
growing time series. See todo/todo_sa_data_retention_3yr.md.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-13
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_037_sa_storage_metrics.sql")


def upgrade():
    if table_exists(op, "sa_storage_metrics"):
        logger.info("sa_storage_metrics already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `sa_storage_metrics`;")
