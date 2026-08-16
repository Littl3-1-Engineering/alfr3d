"""routines extensions: recurrence, actions, last_run

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-03
"""

from alembic import op

from run_sql import column_exists, drop_foreign_keys_for_column, index_exists

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # Guarded per-statement rather than a single run_sql_file() call: live
    # databases that picked up some of these columns out-of-band (e.g. a
    # restored backup from before this migration existed) would otherwise
    # fail on "Duplicate column" partway through.
    if not column_exists(op, "routines", "recurrence"):
        op.execute(
            "ALTER TABLE `routines` ADD COLUMN `recurrence` "
            "ENUM('once', 'daily', 'weekly', 'weekdays') DEFAULT 'daily' AFTER `enabled`;"
        )
    if not column_exists(op, "routines", "actions"):
        op.execute("ALTER TABLE `routines` ADD COLUMN `actions` JSON NULL AFTER `recurrence`;")
    if not column_exists(op, "routines", "last_run"):
        op.execute("ALTER TABLE `routines` ADD COLUMN `last_run` TIMESTAMP NULL AFTER `actions`;")
    op.execute("UPDATE routines SET recurrence = 'daily' WHERE recurrence IS NULL;")
    if not index_exists(op, "routines", "idx_routines_environment_time"):
        op.execute(
            "CREATE INDEX idx_routines_environment_time ON routines(environment_id, time, enabled);"
        )


def downgrade():
    drop_foreign_keys_for_column(op, "routines", "environment_id")
    op.execute("DROP INDEX idx_routines_environment_time ON `routines`;")
    op.execute(
        "ALTER TABLE `routines` DROP COLUMN `last_run`, "
        "DROP COLUMN `actions`, DROP COLUMN `recurrence`;"
    )
