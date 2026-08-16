"""iot device link: device_id foreign key on smarthome_devices

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import drop_foreign_keys_for_column, run_sql_file, sql_path

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_008_iot_device_link.sql"))


def downgrade():
    drop_foreign_keys_for_column(op, "smarthome_devices", "device_id")
    op.execute("ALTER TABLE `smarthome_devices` DROP INDEX idx_device_id;")
    op.execute("ALTER TABLE `smarthome_devices` DROP COLUMN `device_id`;")
