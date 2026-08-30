"""Durable household event log: household_events table

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_026_household_events.sql")


def upgrade():
    if table_exists(op, "household_events"):
        logger.info("household_events already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS household_events;")
