"""iot tables: smarthome_devices and device_command_history

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_002_iot.sql"))


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_device_command_history_event`;")
    op.execute("DROP TABLE IF EXISTS `device_command_history`;")
    op.execute("DROP TABLE IF EXISTS `smarthome_devices`;")
    op.execute(
        "DELETE FROM `config` WHERE `name` IN ('iot_provider', 'ha_url', 'ha_token', 'st_pat');"
    )
