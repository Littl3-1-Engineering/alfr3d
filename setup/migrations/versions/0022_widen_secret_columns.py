"""Widen secret-bearing columns: config.value to TEXT, esphome_nodes.psk to VARCHAR(512)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-22
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_021_widen_secret_columns.sql"))


def downgrade():
    op.execute("ALTER TABLE config MODIFY value VARCHAR(512) NULL DEFAULT NULL;")
    op.execute("ALTER TABLE esphome_nodes MODIFY psk VARCHAR(255) NULL DEFAULT NULL;")
