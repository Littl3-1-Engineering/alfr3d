"""Time-of-day-aware quips: Morning/Sunrise/Sunset routines can speak; re-type "Hello sunshine"

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-04
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_035_time_of_day_quips.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute(
        "UPDATE quips SET type = 'smart' " "WHERE type = 'morning' AND quips = 'Hello sunshine';"
    )
    op.execute(
        "DELETE FROM quips WHERE type IN ('morning', 'sunrise', 'sunset') "
        "AND quips <> 'Hello sunshine';"
    )
