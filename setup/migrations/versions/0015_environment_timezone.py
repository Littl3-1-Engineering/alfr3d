"""environment timezone column for time-based checks

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-06
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_015_environment_timezone.sql"))


def downgrade():
    op.execute("ALTER TABLE environment DROP COLUMN timezone;")
