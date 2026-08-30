"""SA-2: attention_telemetry_history table

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_028_attention_telemetry_history.sql")


def upgrade():
    if table_exists(op, "attention_telemetry_history"):
        logger.info("attention_telemetry_history already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS attention_telemetry_history;")
