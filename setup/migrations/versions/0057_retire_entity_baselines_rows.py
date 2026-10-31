"""Clear the entity_baselines rows nothing reads or writes any more

See migration_051's own comment.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-31
"""

from alembic import op

from run_sql import table_exists

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    if table_exists(op, "entity_baselines"):
        op.execute(
            "DELETE FROM `entity_baselines` "
            "WHERE `entity_type` IN ('device', 'household', 'room');"
        )


def downgrade():
    # The retired rows are recomputed by nothing; the learners hold their own profiles.
    pass
