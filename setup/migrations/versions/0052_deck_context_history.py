"""deck_context_history: the Deck's device context and surface state as history

LF-0c of the SA learning foundation (todo/sa/todo_deck_learning_stream.md). The device-snapshot
and surface-state reports were stored as one overwritten config value each; this appends a row on
every change (plus a 30-minute heartbeat) so DND, charging, network and the rest can be learned
from. See migration_047's own comment.

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-10
"""

from alembic import op

from run_sql import run_sql_file, sql_path, storage_metrics_proc_sql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_047_deck_context_history.sql")

_PRE_0052_METRICS_TABLES = (
    "household_events",
    "card_interactions",
    "attention_telemetry_history",
    "device_location_history",
    "entity_baselines",
    "device_history",
    "smarthome_sensor_history",
    "environment_history",
    "calendar_events",
    "listening_history",
    "device_command_history",
    "sa_inferences",
)


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_deck_context_history_event`;")
    op.execute("DROP TABLE IF EXISTS `deck_context_history`;")
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    op.execute(storage_metrics_proc_sql(_PRE_0052_METRICS_TABLES))
