"""speaker groups table for whole-home audio casting

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-06
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_014_speaker_groups.sql"))


def downgrade():
    op.execute("DROP TABLE IF EXISTS speaker_groups;")
