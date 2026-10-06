"""Add kanji_wisdom table -- the backend-owned daily kanji quote list

Backs GET /api/kanji/today, which the Deck (and later the web frontend) show one entry of per
day. Seeded with the same 30 entries as the Deck's built-in fallback list.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-06
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_042_kanji_wisdom.sql")


def upgrade():
    if table_exists(op, "kanji_wisdom"):
        logger.info("kanji_wisdom already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `kanji_wisdom`;")
