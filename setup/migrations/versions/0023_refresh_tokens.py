"""Auth + RBAC: refresh_tokens table, fix erroneous quoted password_hash seed value

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-22
"""

import logging

from alembic import op

from run_sql import run_sql_file, split_sql_script, sql_path, table_exists

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_022_refresh_tokens.sql")


def upgrade():
    if table_exists(op, "refresh_tokens"):
        logger.info("refresh_tokens already present; skipping CREATE TABLE")
        # The trailing UPDATE (password_hash quoting fix) still needs to run.
        with open(_SQL_FILE, encoding="utf-8") as handle:
            statements = split_sql_script(handle.read())
        op.execute(statements[-1])
    else:
        run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS refresh_tokens;")
