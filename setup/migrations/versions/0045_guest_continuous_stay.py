"""Add user.continuous_stay_since -- start of a guest's current unbroken stay

Backs continuous-stay guest decay: a guest's influence on SA card priority and the household
"energy" score fades (and can go negative) the longer they've been continuously present, so a
brief drop-in and a multi-week houseguest are no longer treated identically. NULL for non-guests,
or for a guest not currently mid-stay. Written only by service_user.app.update_user_state() on an
offline->online transition -- see its CONTINUOUS_STAY_RESET_GAP_HOURS handling.

Backfills already-online guests from their current last_online, since there's no earlier signal
to reconstruct a real stay-start -- a known approximation that self-corrects the next time that
guest has a real departure gap.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-18
"""

from alembic import op

from run_sql import column_exists

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists(op, "user", "continuous_stay_since"):
        op.execute(
            "ALTER TABLE `user` ADD COLUMN `continuous_stay_since` DATETIME NULL DEFAULT NULL "
            "AFTER `last_online`;"
        )
        op.execute(
            """
            UPDATE `user` u
            JOIN `user_types` ut ON u.type = ut.id
            JOIN `states` s ON u.state = s.id
            SET u.continuous_stay_since = u.last_online
            WHERE ut.type = 'guest' AND s.state = 'online';
            """
        )


def downgrade():
    op.execute("ALTER TABLE `user` DROP COLUMN `continuous_stay_since`;")
