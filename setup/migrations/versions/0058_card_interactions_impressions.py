"""card_interactions learns what an impression is

See migration_052's own comment.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-31
"""

from alembic import op

from run_sql import column_exists

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

_NEW_COLUMNS = ("surface", "impression_id", "visible_ms", "detail")


def upgrade():
    if column_exists(op, "card_interactions", "impression_id"):
        return
    op.execute(
        "ALTER TABLE `card_interactions` "
        "MODIFY COLUMN `action` ENUM('shown', 'tapped', 'dismissed', 'expired', 'impression') "
        "NOT NULL, "
        "ADD COLUMN `surface` VARCHAR(16) NULL DEFAULT NULL AFTER `user_id`, "
        "ADD COLUMN `impression_id` VARCHAR(36) NULL DEFAULT NULL AFTER `surface`, "
        "ADD COLUMN `visible_ms` INT UNSIGNED NULL DEFAULT NULL AFTER `impression_id`, "
        "ADD COLUMN `detail` VARCHAR(64) NULL DEFAULT NULL AFTER `visible_ms`, "
        "ADD INDEX `idx_card_interactions_impression` (`impression_id`);"
    )


def downgrade():
    op.execute("DELETE FROM `card_interactions` WHERE `action` = 'impression';")
    op.execute(
        "ALTER TABLE `card_interactions` DROP INDEX `idx_card_interactions_impression`, "
        + ", ".join(f"DROP COLUMN `{c}`" for c in _NEW_COLUMNS)
        + ", MODIFY COLUMN `action` ENUM('shown', 'tapped', 'dismissed', 'expired') NOT NULL;"
    )
