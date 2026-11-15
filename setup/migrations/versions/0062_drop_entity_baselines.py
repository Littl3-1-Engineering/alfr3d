"""Drop the entity_baselines table (LF-4 complete)

Every rule that read it now reads a learner profile or inference instead (device rhythm,
presence/stay, scalar, household day), and compute_entity_baselines() is gone. Migration 0057
already cleared the device/household/room rows; the 8 leftover `user` rows had no reader.
The storage-metrics procedure stops tracking it.

Take a backup first (setup/db_backup_daily.sh keeps a nightly one).

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-15
"""

from alembic import op

from run_sql import (
    run_sql_file,
    sql_path,
    storage_metrics_proc_sql,
    table_exists,
)

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

# The table list record_sa_storage_metrics_proc() tracked as of 0052, with and without it.
_TRACKED_WITHOUT = (
    "household_events",
    "card_interactions",
    "attention_telemetry_history",
    "device_location_history",
    "device_history",
    "smarthome_sensor_history",
    "environment_history",
    "calendar_events",
    "listening_history",
    "device_command_history",
    "sa_inferences",
    "deck_context_history",
)
_TRACKED_WITH = _TRACKED_WITHOUT[:4] + ("entity_baselines",) + _TRACKED_WITHOUT[4:]

# The raw-SQL files that built the table up to its final shape, in order (0025, 0033, 0035,
# 0044, 0055), so a downgrade lets those revisions re-apply.
_REBUILD_SQL = (
    "migration_023_entity_baselines.sql",
    "migration_031_departure_anomaly.sql",
    "migration_033_entity_baselines_generalize.sql",
    "migration_041_entity_baselines_climate.sql",
    "migration_050_entity_baselines_active_hours.sql",
)


def _recreate_proc(tables):
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    op.execute(storage_metrics_proc_sql(tables))


def upgrade():
    _recreate_proc(_TRACKED_WITHOUT)
    op.execute("DROP TABLE IF EXISTS `entity_baselines`;")


def downgrade():
    # Empty: nothing recomputes the old rows, and the learners hold their own profiles.
    if not table_exists(op, "entity_baselines"):
        for name in _REBUILD_SQL:
            run_sql_file(op, sql_path(name))
    _recreate_proc(_TRACKED_WITH)
