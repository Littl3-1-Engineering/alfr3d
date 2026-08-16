"""dedupe smarthome_devices and restore the unique key

setup/migration_017_iot_dedupe.sql
The unique_source_device key was missing on some live databases, so HA/ST
syncs inserted fresh copies of every entity on each 15-minute run (32k+ rows,
hundreds of copies per entity), flooding the Domain DEVICES page and crashing
the frontend. This revision dedupes the table and restores the key.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-12
"""

import logging

import sqlalchemy as sa
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    if bind is None:
        return False
    rows = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
            "AND INDEX_NAME = :index"
        ),
        {"table": table, "index": index},
    ).fetchone()
    return bool(rows and rows[0])


def upgrade():
    # Fresh databases get unique_source_device from migration 0003, so the
    # dedupe/repair below is only needed on live databases that lost the key.
    if _index_exists("smarthome_devices", "unique_source_device"):
        logger.info("unique_source_device already present; skipping dedupe")
        return
    run_sql_file(op, sql_path("migration_017_iot_dedupe.sql"))


def downgrade():
    # Deleted duplicate rows cannot be reconstructed, and dropping the unique
    # key would re-open the duplication bug; safe no-op.
    pass
