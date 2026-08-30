"""SA-10: generalise entity_baselines (entity_type gains 'room'/'household', min_sample_count)

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-30
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "entity_baselines", "min_sample_count"):
        logger.info("entity_baselines.min_sample_count already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_033_entity_baselines_generalize.sql"))


def downgrade():
    if column_exists(op, "entity_baselines", "min_sample_count"):
        op.execute("DELETE FROM entity_baselines WHERE entity_type IN ('room', 'household');")
        op.execute(
            "ALTER TABLE entity_baselines "
            "DROP COLUMN min_sample_count, "
            "DROP COLUMN typical_last_activity_hour, "
            "MODIFY COLUMN entity_type ENUM('device', 'smarthome_device', 'user') NOT NULL;"
        )
