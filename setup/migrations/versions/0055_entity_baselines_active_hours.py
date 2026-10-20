"""entity_baselines.active_hours_mask -- hours of the day a device is usually online

See migration_050's own comment.

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-20
"""

from alembic import op

from run_sql import column_exists

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists(op, "entity_baselines", "active_hours_mask"):
        op.execute(
            "ALTER TABLE `entity_baselines` ADD COLUMN `active_hours_mask` INT UNSIGNED NULL "
            "DEFAULT NULL AFTER `typical_last_activity_hour`;"
        )


def downgrade():
    op.execute("ALTER TABLE `entity_baselines` DROP COLUMN `active_hours_mask`;")
