"""Auth + RBAC: refresh_tokens table, fix erroneous quoted password_hash seed value

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-22
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_022_refresh_tokens.sql"))


def downgrade():
    op.execute("DROP TABLE IF EXISTS refresh_tokens;")
