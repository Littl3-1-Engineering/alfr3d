"""Add user.title -- free-text form of address

Backs the "how should Alfred address me" feature: a free-text field the owner (and later other
residents/guests) can set to whatever they want Alfred to call them ("boss", "Dr. Athos", a first
name, ...). Left NULL, the speak-pipeline prompt falls back to the user's name and is told never
to use gendered honorifics like "sir"/"madam". See services/service_speak/personality.py's
get_owner_address()/build_llm_system_prompt().

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-04
"""

from alembic import op

from run_sql import column_exists

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists(op, "user", "title"):
        op.execute(
            "ALTER TABLE `user` ADD COLUMN `title` VARCHAR(64) NULL DEFAULT NULL AFTER `about_me`;"
        )


def downgrade():
    op.execute("ALTER TABLE `user` DROP COLUMN `title`;")
