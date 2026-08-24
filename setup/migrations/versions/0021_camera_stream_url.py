"""Camera stream URL: stream_url column on device

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-21
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "device", "stream_url"):
        logger.info("device.stream_url already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_020_camera_stream_url.sql"))


def downgrade():
    if column_exists(op, "device", "stream_url"):
        op.execute("ALTER TABLE device DROP COLUMN stream_url;")
