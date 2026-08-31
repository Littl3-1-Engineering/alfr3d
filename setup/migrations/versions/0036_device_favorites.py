"""Add device_favorites table (Nexus quick-controls pane)

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-31
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_034_device_favorites.sql")


def upgrade():
    if table_exists(op, "device_favorites"):
        logger.info("device_favorites already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS device_favorites;")
