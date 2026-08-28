"""Cross-surface continuity card: routines.updated_at

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-28
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_024_routines_updated_at.sql")


def upgrade():
    if column_exists(op, "routines", "updated_at"):
        logger.info("routines.updated_at already present; skipping ALTER")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    if column_exists(op, "routines", "updated_at"):
        op.execute("ALTER TABLE routines DROP COLUMN updated_at;")
