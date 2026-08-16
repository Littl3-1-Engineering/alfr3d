"""calendar cleanup: replace calendar cleanup trigger with scheduled event

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import event_exists, run_sql_file, sql_path

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # The documented setup flow loads createTables.sql (which already creates
    # this same event) as root, then runs migrations as the unprivileged app
    # DB user -- which can DROP EVENT IF EXISTS `cleanup_old_calendar_events`
    # fine (a trigger, owned by the app user) but can't DROP/recreate an event
    # owned by root without the SYSTEM_USER privilege. If the event already
    # exists with the intended schedule/body, skip re-creating it instead of
    # failing on that DROP.
    if event_exists(op, "cleanup_calendar_events_event"):
        op.execute("DROP TRIGGER IF EXISTS `cleanup_old_calendar_events`;")
        return
    run_sql_file(op, sql_path("migration_001_calendar_cleanup.sql"))


def downgrade():
    op.execute("DROP EVENT IF EXISTS `cleanup_calendar_events_event`;")
