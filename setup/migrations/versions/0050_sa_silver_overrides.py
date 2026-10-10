"""SA silver overrides: sa_data_exclusions and sa_sensor_aliases

LF-2 of the SA learning foundation (todo/sa/todo_lf2_silver_gold.md). Two small hand-editable
tables the nightly silver build reads: time windows of rows to drop (test bursts) and the stable
identity of retired sensor ids. Seeds only what the todos already document. See
migration_045's own comment.

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-10
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_045_sa_silver_overrides.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `sa_sensor_aliases`;")
    op.execute("DROP TABLE IF EXISTS `sa_data_exclusions`;")
