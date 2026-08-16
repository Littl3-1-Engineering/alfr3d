"""remove auto-created device rows from HA/ST sync

setup/migration_016_iot_device_cleanup.sql
Phase 16 of the IoT plan: sync no longer auto-creates `device` rows for
unmatched smarthome devices. This revision cleans up rows that previous
syncs created (identified by IP = '0.0.0.0').

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-07
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_016_iot_device_cleanup.sql"))


def downgrade():
    # Data deleted by this migration cannot be reconstructed; safe no-op.
    pass
