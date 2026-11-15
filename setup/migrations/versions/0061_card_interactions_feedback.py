"""card_interactions learns acked and not_useful

See migration_055's own comment.

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-14
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade():
    # MODIFY with the full enum is idempotent: re-running it changes nothing.
    op.execute(
        "ALTER TABLE `card_interactions` MODIFY COLUMN `action` "
        "ENUM('shown', 'tapped', 'dismissed', 'expired', 'impression', 'acked', 'not_useful') "
        "NOT NULL;"
    )


def downgrade():
    op.execute("DELETE FROM `card_interactions` WHERE `action` IN ('acked', 'not_useful');")
    op.execute(
        "ALTER TABLE `card_interactions` MODIFY COLUMN `action` "
        "ENUM('shown', 'tapped', 'dismissed', 'expired', 'impression') NOT NULL;"
    )
