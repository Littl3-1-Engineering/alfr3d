"""weather forecast columns (rain probability, forecast temp/conditions)

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-16
"""

from alembic import op

from run_sql import run_sql_file, sql_path

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    run_sql_file(op, sql_path("migration_018_weather_forecast.sql"))


def downgrade():
    op.execute("ALTER TABLE environment DROP COLUMN forecast_updated_at;")
    op.execute("ALTER TABLE environment DROP COLUMN forecast_conditions;")
    op.execute("ALTER TABLE environment DROP COLUMN forecast_temp;")
    op.execute("ALTER TABLE environment DROP COLUMN forecast_rain_probability;")
