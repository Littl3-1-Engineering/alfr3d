"""baseline: initial ALFR3D schema from setup/createTables.sql

Revision ID: 0001
Revises:
Create Date: 2026-08-03
"""

import logging

import sqlalchemy as sa
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_BASE_TABLES = [
    "integrations_tokens",
    "calendar_events",
    "quips",
    "config",
    "environment",
    "routines",
    "device_history",
    "device",
    "states",
    "device_types",
    "user_types",
    "user",
]


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    if bind is None:
        return False
    rows = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :name"
        ),
        {"name": table},
    ).fetchone()
    return bool(rows and rows[0])


def upgrade():
    if _table_exists("user"):
        logger.info("baseline schema already present; skipping createTables.sql")
        return
    run_sql_file(op, sql_path("createTables.sql"))


def downgrade():
    op.execute("SET FOREIGN_KEY_CHECKS = 0;")
    for table in _BASE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS `{table}`;")
    op.execute("SET FOREIGN_KEY_CHECKS = 1;")
    op.execute("DROP EVENT IF EXISTS `cleanup_device_history_event`;")
    op.execute("DROP EVENT IF EXISTS `cleanup_calendar_events_event`;")
    op.execute("DROP TRIGGER IF EXISTS `before_device_update`;")
