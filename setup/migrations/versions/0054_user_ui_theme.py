"""Add user.ui_theme -- the person's chosen UI theme, shared across web and Deck

See migration_049's own comment and todo/todo_theme_sync_deck.md.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-12
"""

from alembic import op

from run_sql import column_exists

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists(op, "user", "ui_theme"):
        op.execute(
            "ALTER TABLE `user` ADD COLUMN `ui_theme` VARCHAR(32) NULL DEFAULT NULL AFTER `title`;"
        )


def downgrade():
    op.execute("ALTER TABLE `user` DROP COLUMN `ui_theme`;")
