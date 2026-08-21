"""Camera stream URL: stream_url column on device

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-21
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_020_camera_stream_url.sql"))


def downgrade():
    op.execute("ALTER TABLE device DROP COLUMN stream_url;")
