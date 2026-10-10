"""SA inference contract: sa_profiles and sa_inferences

LF-3 of the SA learning foundation (todo/sa/todo_lf3_presence_learner.md). The two tables every
learner and rule shares: what a learner fitted, and a scored statement about a subject with a
probability and a confidence. See migration_046's own comment.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-10
"""

from alembic import op

from run_sql import run_sql_file, sql_path, storage_metrics_proc_sql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_046_sa_inference_contract.sql")

_PRE_0051_METRICS_TABLES = (
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
)


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_sa_inferences_event`;")
    op.execute("DROP TABLE IF EXISTS `sa_inferences`;")
    op.execute("DROP TABLE IF EXISTS `sa_profiles`;")
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    op.execute(storage_metrics_proc_sql(_PRE_0051_METRICS_TABLES))
