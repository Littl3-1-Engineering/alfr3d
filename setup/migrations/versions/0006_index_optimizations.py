"""index optimizations for hot query paths

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import drop_foreign_keys_for_column, index_exists

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

# (table, index, column expression) for CREATE INDEX -- column expression can
# differ from the FK column name used above for the downgrade path.
_CREATE = [
    ("device_history", "idx_device_history_device_id", "device_id"),
    ("device_history", "idx_device_history_timestamp", "timestamp"),
    ("config", "idx_config_name", "name"),
    ("personality", "idx_personality_type", "type"),
    ("quips", "idx_quips_type", "type"),
    ("environment", "idx_environment_name", "name"),
    ("calendar_events", "idx_calendar_events_end_time", "end_time"),
]


def upgrade():
    # Guarded per-index rather than a single run_sql_file() call: a live
    # database that already picked up some of these indexes out-of-band
    # (e.g. a restored backup older than this migration) would otherwise
    # fail on "Duplicate key name" partway through.
    for table, index, column in _CREATE:
        if not index_exists(op, table, index):
            op.execute(f"CREATE INDEX {index} ON {table}({column});")


def downgrade():
    for table, index, column in reversed(_INDEXES):
        if column:
            drop_foreign_keys_for_column(op, table, column)
        op.execute(f"DROP INDEX {index} ON `{table}`;")
