"""Backfill user_types.owner for databases that predate it

createTables.sql already seeds `user_types` with 'owner' (id 4), but 0001_baseline only runs
createTables.sql when the `user` table doesn't exist yet -- any database migrated before 'owner'
was added to createTables.sql (services/service_api/auth/permissions.py's e4caa6f auth+RBAC
change) never got that row and has no other path to it. Backend routes already resolve `type` by
name (`SELECT id FROM user_types WHERE type = %s`, routes/users.py), so once this row exists
'owner' is fully usable end-to-end with no other backend change.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-24
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade():
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT id FROM user_types WHERE type = 'owner'")).fetchone()
    if row:
        logger.info("user_types.owner already present; skipping")
        return
    op.execute("INSERT INTO user_types (type) VALUES ('owner');")


def downgrade():
    op.execute("DELETE FROM user_types WHERE type = 'owner';")
