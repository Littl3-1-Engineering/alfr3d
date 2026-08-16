"""personality matrix: personality and context tables plus LLM config

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_004_personality.sql"))


def downgrade():
    op.execute("DROP TABLE IF EXISTS `context`;")
    op.execute("DROP TABLE IF EXISTS `personality`;")
    op.execute("DELETE FROM `config` WHERE `name` IN ('llm_api_key', 'llm_usage_limit');")
    op.execute("ALTER TABLE `config` MODIFY COLUMN `value` VARCHAR(255);")
