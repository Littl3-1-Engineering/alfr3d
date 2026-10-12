"""sa_shadow_comparison: the learner-versus-legacy comparison as history

The shadow log lines vanished on every container restart, so the evidence for the rule cutover
review could not be counted. See migration_048's own comment.

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-12
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_048_sa_shadow_comparison.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_sa_shadow_comparison_event`;")
    op.execute("DROP TABLE IF EXISTS `sa_shadow_comparison`;")
