"""Structured subject/verb fields on household_events

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-29
"""

import logging

from alembic import op

from run_sql import column_exists, run_sql_file, sql_path

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    if column_exists(op, "household_events", "subject_type"):
        logger.info("household_events.subject_type already present; skipping ALTER")
        return
    run_sql_file(op, sql_path("migration_027_household_events_structured_fields.sql"))


def downgrade():
    if column_exists(op, "household_events", "verb"):
        op.execute(
            "ALTER TABLE household_events "
            "DROP COLUMN subject_type, DROP COLUMN subject_id, DROP COLUMN verb;"
        )
