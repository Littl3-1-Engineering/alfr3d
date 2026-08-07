"""routines extensions: recurrence, actions, last_run

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-03
"""
from alembic import op

from run_sql import drop_foreign_keys_for_column, run_sql_file, sql_path

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_003_routines.sql"))


def downgrade():
    drop_foreign_keys_for_column(op, "routines", "environment_id")
    op.execute("DROP INDEX idx_routines_environment_time ON `routines`;")
    op.execute("ALTER TABLE `routines` DROP COLUMN `last_run`, DROP COLUMN `actions`, DROP COLUMN `recurrence`;")
