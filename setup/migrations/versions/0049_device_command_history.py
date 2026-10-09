"""device_command_history returns as a real command log (params, outcome, origin)

Migration 043/0048 dropped the never-written original table; that lost a genuinely useful SA
learning signal (command parameters, failures, who issued what). Migration 044 recreates it with
a shape built for learning and no FK to smarthome_devices. Every command is written by
common/device_commands.record_device_command() from the three low-level senders. See
migration_044's own comment.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-09
"""

from alembic import op

from run_sql import run_sql_file, sql_path, storage_metrics_proc_sql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_044_device_command_history.sql")

_PRE_0049_METRICS_TABLES = (
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
)


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    # Leaves the schema as 0048 left it: no device_command_history at all (0048's own
    # downgrade restores the original shape if the chain goes further back).
    op.execute("DROP EVENT IF EXISTS `cleanup_device_command_history_event`;")
    op.execute("DROP TABLE IF EXISTS `device_command_history`;")
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    op.execute(storage_metrics_proc_sql(_PRE_0049_METRICS_TABLES))
