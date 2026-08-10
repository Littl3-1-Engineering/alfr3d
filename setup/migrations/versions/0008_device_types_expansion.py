"""device types expansion for HA/ST domains

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_NEW_TYPES = [
    "fan",
    "climate",
    "cover",
    "lock",
    "media_player",
    "sensor",
    "binary_sensor",
    "camera",
]


def upgrade():
    run_sql_file(op, sql_path("migration_007_device_types_expansion.sql"))


def downgrade():
    for device_type in _NEW_TYPES:
        op.execute(f"DELETE FROM `device_types` WHERE `type` = '{device_type}';")
