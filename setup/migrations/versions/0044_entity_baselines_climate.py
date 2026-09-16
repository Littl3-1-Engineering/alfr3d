"""SA-9 Phase 2: entity_baselines gains time_of_day_bucket + typical_median_value

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-16
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "entity_baselines", "time_of_day_bucket"):
        logger.info("entity_baselines.time_of_day_bucket already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_041_entity_baselines_climate.sql"))


def downgrade():
    if column_exists(op, "entity_baselines", "time_of_day_bucket"):
        op.execute(
            "ALTER TABLE entity_baselines "
            "DROP INDEX unique_entity, "
            "DROP COLUMN time_of_day_bucket, "
            "DROP COLUMN typical_median_value, "
            "ADD UNIQUE KEY unique_entity (entity_type, entity_id, day_bucket);"
        )
