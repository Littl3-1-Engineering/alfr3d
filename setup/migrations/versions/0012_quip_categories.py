"""quip categories: category column on quips table

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-06
"""

import logging

import sqlalchemy as sa
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if bind is None:
        return False
    rows = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
            "AND COLUMN_NAME = :column"
        ),
        {"table": table, "column": column},
    ).fetchone()
    return bool(rows and rows[0])


def upgrade():
    if _column_exists("quips", "category"):
        logger.info("quips.category already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_011_quip_categories.sql"))


def downgrade():
    if _column_exists("quips", "category"):
        op.execute("ALTER TABLE quips DROP COLUMN category;")
