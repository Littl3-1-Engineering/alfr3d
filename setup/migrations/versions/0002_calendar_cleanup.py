"""calendar cleanup: replace calendar cleanup trigger with scheduled event

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-03
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_001_calendar_cleanup.sql"))


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_calendar_events_event`;")
