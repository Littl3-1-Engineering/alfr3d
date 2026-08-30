"""SA-3: per-user departure baselines (entity_baselines gains 'user' + day_bucket)

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "entity_baselines", "day_bucket"):
        logger.info("entity_baselines.day_bucket already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_031_departure_anomaly.sql"))


def downgrade():
    if column_exists(op, "entity_baselines", "day_bucket"):
        op.execute("DELETE FROM entity_baselines WHERE entity_type = 'user';")
        op.execute(
            "ALTER TABLE entity_baselines "
            "DROP INDEX unique_entity, "
            "DROP COLUMN day_bucket, "
            "MODIFY COLUMN entity_type ENUM('device', 'smarthome_device') NOT NULL, "
            "ADD UNIQUE KEY unique_entity (entity_type, entity_id);"
        )
