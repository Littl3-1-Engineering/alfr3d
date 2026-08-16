"""slow query indexes from ticket #21

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import drop_foreign_keys_for_column, run_sql_file, sql_path

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_INDEXES = [
    ("device", "idx_device_mac", "MAC"),
    ("device", "idx_device_last_online", "last_online"),
    ("device", "idx_device_user_id", "user_id"),
    ("user", "idx_user_username", "username"),
    ("user", "idx_user_state", "state"),
    ("user", "idx_user_last_online", "last_online"),
    ("personality", "idx_personality_type_env", None),
    ("calendar_events", "idx_calendar_events_start_time", None),
]


def upgrade():
    run_sql_file(op, sql_path("migration_010_slow_query_indexes.sql"))


def downgrade():
    for table, index, column in reversed(_INDEXES):
        if column:
            drop_foreign_keys_for_column(op, table, column)
        op.execute(f"DROP INDEX {index} ON `{table}`;")
