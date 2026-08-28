"""Rhythm-break anomaly cards: entity_baselines table

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-28
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_023_entity_baselines.sql")


def upgrade():
    if table_exists(op, "entity_baselines"):
        logger.info("entity_baselines already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS entity_baselines;")
