"""ESPHome integration: esp_entity_id column + esphome_nodes table

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-21
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_019_esphome.sql"))


def downgrade():
    op.execute("DELETE FROM config WHERE name = 'esphome_enabled';")
    op.execute("DROP TABLE IF EXISTS esphome_nodes;")
    op.execute("ALTER TABLE smarthome_devices DROP INDEX unique_source_device;")
    op.execute(
        "ALTER TABLE smarthome_devices ADD UNIQUE KEY unique_source_device "
        "(source, (COALESCE(ha_entity_id, st_device_id)));"
    )
    op.execute("ALTER TABLE smarthome_devices DROP COLUMN esp_entity_id;")
