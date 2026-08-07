"""index optimizations for hot query paths

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03
"""
from alembic import op

from run_sql import drop_foreign_keys_for_column, run_sql_file, sql_path

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_INDEXES = [
    ("device_history", "idx_device_history_device_id", "device_id"),
    ("device_history", "idx_device_history_timestamp", None),
    ("config", "idx_config_name", None),
    ("personality", "idx_personality_type", None),
    ("quips", "idx_quips_type", None),
    ("environment", "idx_environment_name", None),
    ("calendar_events", "idx_calendar_events_end_time", None),
]


def upgrade():
    run_sql_file(op, sql_path("migration_005_indexes.sql"))


def downgrade():
    for table, index, column in reversed(_INDEXES):
        if column:
            drop_foreign_keys_for_column(op, table, column)
        op.execute(f"DROP INDEX {index} ON `{table}`;")
