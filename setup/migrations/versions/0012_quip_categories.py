"""quip categories: category column on quips table

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-06
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_011_quip_categories.sql"))


def downgrade():
    op.execute("ALTER TABLE quips DROP COLUMN category;")
