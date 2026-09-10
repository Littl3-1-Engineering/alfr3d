"""device_location_history table

Per-device geolocation history reported by ALFR3D Deck via POST /api/context/device-location
(routes/context.py). Keyed by the Deck install's stable UUID; user_id denormalized from the
JWT; device_id NULL until a later device-linking step. Data-collection pipeline only -- no SA
rule consumes it yet. See todo/todo_device_location_reporting.md.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-10
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path, table_exists

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_036_device_location_history.sql")


def upgrade():
    if table_exists(op, "device_location_history"):
        logger.info("device_location_history already present; skipping CREATE TABLE")
        return
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_device_location_history_event`;")
    op.execute("DROP TABLE IF EXISTS `device_location_history`;")
