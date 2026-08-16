"""personality context tracking: last_text and last_spoke_time

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_006_personality_context.sql"))


def downgrade():
    op.execute("ALTER TABLE `context` DROP INDEX idx_last_spoke_time;")
    op.execute("ALTER TABLE `context` DROP COLUMN `last_spoke_time`, DROP COLUMN `last_text`;")
