"""SA-7: calendar conferencing metadata (conference_uri/conference_solution)

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "calendar_events", "conference_uri"):
        logger.info("calendar_events.conference_uri already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_030_calendar_conferencing.sql"))


def downgrade():
    if column_exists(op, "calendar_events", "conference_solution"):
        op.execute(
            "ALTER TABLE calendar_events "
            "DROP COLUMN conference_uri, DROP COLUMN conference_solution;"
        )
