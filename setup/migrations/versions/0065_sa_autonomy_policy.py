"""The layer-3 autonomy policy and its audit log (Timeline "Layer 3 3/4")

Two small tables, both created EMPTY: `sa_autonomy_policy` (a level per action type, scope and
context; a missing row is level 0) and `sa_autonomy_log` (append-only record of every promotion,
demotion, kill and reset). Nothing reads them to execute anything in this release: there is no
executor. See migration_058's own comment and todo/sa/todo_l3_proposal_policy_contract.md.

Take a backup first (setup/db_backup_daily.sh keeps a nightly one). Downgrade drops both tables;
nothing else reads them.

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-19
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_058_sa_autonomy_policy.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `sa_autonomy_log`;")
    op.execute("DROP TABLE IF EXISTS `sa_autonomy_policy`;")
