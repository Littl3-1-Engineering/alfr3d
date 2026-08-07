"""listening history table for the music recommender

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-06
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_013_listening_history.sql"))


def downgrade():
    op.execute("DROP TABLE IF EXISTS listening_history;")
