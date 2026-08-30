"""SA-1: card_interactions table

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_029_card_interactions.sql")


def upgrade():
    if table_exists(op, "card_interactions"):
        logger.info("card_interactions already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS card_interactions;")
