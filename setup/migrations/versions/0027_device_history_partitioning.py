"""device_history retention: RANGE partition by month, drop by partition

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-28
"""

import logging

from alembic import op
from sqlalchemy.exc import OperationalError

from run_sql import (
    drop_foreign_keys_for_column,
    event_exists,
    is_partitioned,
    run_sql_file,
    sql_path,
)

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")

_SQL_FILE = sql_path("migration_025_device_history_partitioning.sql")

# MySQL 8 error 1227: "Access denied; you need (at least one of) the
# SYSTEM_USER privilege(s) for this operation" -- raised when dropping an
# event whose DEFINER holds SYSTEM_USER (e.g. root) from an account that
# doesn't. cleanup_device_history_event was created by root via
# createTables.sql; the app's migration account can't drop it.
_SYSTEM_USER_REQUIRED = "1227"


def _drop_legacy_cleanup_event():
    if not event_exists(op, "cleanup_device_history_event"):
        return
    try:
        op.execute("DROP EVENT `cleanup_device_history_event`;")
    except OperationalError as exc:
        if _SYSTEM_USER_REQUIRED not in str(exc):
            raise
        logger.warning(
            "Can't drop cleanup_device_history_event (needs SYSTEM_USER, "
            "it was created by root) -- leaving it in place. It's now "
            "redundant with maintain_device_history_partitions_event but "
            "harmless: partition drops keep the table within retention "
            "before its daily DELETE would find anything to do. Drop it "
            "manually as root if you want it gone."
        )


def upgrade():
    if is_partitioned(op, "device_history"):
        logger.info("device_history already partitioned; skipping")
        return
    drop_foreign_keys_for_column(op, "device_history", "device_id")
    drop_foreign_keys_for_column(op, "device_history", "environment_id")
    drop_foreign_keys_for_column(op, "device_history", "user_id")
    _drop_legacy_cleanup_event()
    run_sql_file(op, _SQL_FILE)


def downgrade():
    op.execute("DROP EVENT IF EXISTS `maintain_device_history_partitions_event`;")
    op.execute("DROP PROCEDURE IF EXISTS `maintain_device_history_partitions`;")
    if is_partitioned(op, "device_history"):
        op.execute("ALTER TABLE `device_history` REMOVE PARTITIONING;")
    op.execute(
        "ALTER TABLE `device_history` ADD FOREIGN KEY (device_id) REFERENCES `device` (`id`);"
    )
    op.execute(
        "ALTER TABLE `device_history` ADD FOREIGN KEY (environment_id) "
        "REFERENCES `environment` (`id`);"
    )
    op.execute("ALTER TABLE `device_history` ADD FOREIGN KEY (user_id) REFERENCES `user` (`id`);")
    if not event_exists(op, "cleanup_device_history_event"):
        op.execute(
            "CREATE EVENT `cleanup_device_history_event` "
            "ON SCHEDULE EVERY 1 DAY "
            "DO DELETE FROM device_history WHERE timestamp < DATE_SUB(NOW(), INTERVAL 180 DAY);"
        )
