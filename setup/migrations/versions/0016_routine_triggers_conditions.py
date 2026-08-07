"""routine triggers and conditions (WHEN / IF / THEN)

setup/migration_009_routines_v2.sql existed on disk but was never wired into
the alembic chain (0009_iot_device_link revises straight to
0010_slow_query_indexes). The columns it adds are already read/written by
service_api/routes/routines.py and service_daemon/utils/util_routines.py, so
a fresh `alembic upgrade head` was silently missing them.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-06
"""
from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_009_routines_v2.sql"))


def downgrade():
    op.execute("ALTER TABLE `routines` DROP COLUMN `conditions`;")
    op.execute("ALTER TABLE `routines` DROP COLUMN `triggers`;")
