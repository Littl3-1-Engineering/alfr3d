"""The context capture ledger table (Timeline "Context learning 2/5")

sa-learner writes the lake's capture ledger here after each nightly silver build and
GET /api/context/ledger reads it (the API does not mount the lake). One small replace-all table,
no retention event. See migration_056's own comment.

Take a backup first (setup/db_backup_daily.sh keeps a nightly one). Downgrade drops the table;
nothing else reads it, and the next nightly run would simply have nowhere to write (it logs and
carries on).

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-19
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_056_sa_context_ledger.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `sa_context_ledger`;")
