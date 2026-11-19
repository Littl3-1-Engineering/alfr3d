"""The discovery screen's findings table (Timeline "Context learning 4/5")

sa-learner writes the nightly covariate screen's findings here (sa/screen.py) and
GET /api/context/findings reads them (the API does not mount the lake). One small append-by-night
table, 90 days kept by the stage itself. See migration_057's own comment.

Take a backup first (setup/db_backup_daily.sh keeps a nightly one). Downgrade drops the table;
nothing else reads it, and the next nightly run would simply have nowhere to write (it logs and
carries on).

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-19
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_SQL_FILE = sql_path("migration_057_sa_covariate_findings.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS `sa_covariate_findings`;")
