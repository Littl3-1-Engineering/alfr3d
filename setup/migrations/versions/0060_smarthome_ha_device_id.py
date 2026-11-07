"""smarthome_devices.ha_device_id (rename-proof Home Assistant identity)

See migration_054's own comment.

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-07
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_054_smarthome_ha_device_id.sql"))


def downgrade():
    op.execute("ALTER TABLE `smarthome_devices` DROP INDEX `idx_smarthome_ha_device_id`;")
    op.execute("ALTER TABLE `smarthome_devices` DROP COLUMN `ha_device_id`;")
