"""SA event-log retention + storage-metrics recording move to DB-native EVENTs

household_events/attention_telemetry_history/card_interactions retention, and the daily
sa_storage_metrics snapshot, move from Python `schedule` jobs in alfr3ddaemon.py to scheduled
EVENTs living inside MySQL itself -- matching device_location_history's own retention (migration
036/038), which was already DB-native. What the database can enforce, the database now enforces,
independent of whether service-daemon happens to be up. See migration_039's own comment.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-13
"""

import logging

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_039_sa_retention_events.sql")


def upgrade():
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_household_events_event`;")
    op.execute("DROP EVENT IF EXISTS `cleanup_attention_telemetry_history_event`;")
    op.execute("DROP EVENT IF EXISTS `cleanup_card_interactions_event`;")
    op.execute("DROP EVENT IF EXISTS `record_sa_storage_metrics_event`;")
    op.execute("DROP PROCEDURE IF EXISTS `record_sa_storage_metrics_proc`;")
    # Deliberately does not reinstate the Python-side schedule jobs this migration's upgrade()
    # superseded -- an alembic downgrade reverses this migration's own DB objects, the same
    # scope every other downgrade() in this chain keeps to (e.g. 0039's). Restoring the
    # application-code path is a git revert, not a migration concern.
