"""add 'switch' to device_types

See migration_053's own comment.

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-01
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_053_device_type_switch.sql"))


def downgrade():
    op.execute("DELETE FROM `device_types` WHERE `type` = 'switch';")
