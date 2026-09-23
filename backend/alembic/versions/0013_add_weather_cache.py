"""Store official forecasts and daily solar times collected by the batch pipeline."""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE weather_forecasts (
            region TEXT NOT NULL,
            forecast_at TIMESTAMPTZ NOT NULL,
            issued_at TIMESTAMPTZ NOT NULL,
            collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            nx INTEGER NOT NULL,
            ny INTEGER NOT NULL,
            temperature_c DOUBLE PRECISION,
            wind_speed_ms DOUBLE PRECISION CHECK (wind_speed_ms >= 0),
            sky INTEGER,
            precipitation_type INTEGER,
            precipitation_probability DOUBLE PRECISION CHECK (precipitation_probability BETWEEN 0 AND 100),
            PRIMARY KEY (region, forecast_at)
        );
        CREATE TABLE solar_times (
            region TEXT NOT NULL,
            solar_date DATE NOT NULL,
            location TEXT NOT NULL,
            sunrise TIME NOT NULL,
            sunset TIME NOT NULL,
            collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (region, solar_date),
            CHECK (sunrise < sunset)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE solar_times; DROP TABLE weather_forecasts")
