"""SA-6: geocode_cache table (address -> lat/lon, for self-hosted routing)

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-30
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if table_exists(op, "geocode_cache"):
        logger.info("geocode_cache already present; skipping create")
        return
    run_sql_file(op, sql_path("migration_032_geocode_cache.sql"))


def downgrade():
    op.execute("DROP TABLE IF EXISTS geocode_cache;")
