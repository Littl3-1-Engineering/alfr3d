"""weather expansion columns (current temp, wind, pressure trend)

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-06
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_012_weather_expansion.sql"))


def downgrade():
    op.execute("ALTER TABLE environment DROP COLUMN pressure_trend;")
    op.execute("ALTER TABLE environment DROP COLUMN wind_dir;")
    op.execute("ALTER TABLE environment DROP COLUMN wind;")
    op.execute("ALTER TABLE environment DROP COLUMN temperature;")
