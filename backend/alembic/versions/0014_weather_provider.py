"""Keep provider provenance for keyless forecasts alongside official sources."""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE weather_forecasts ADD COLUMN provider TEXT NOT NULL DEFAULT 'kma';
        ALTER TABLE weather_forecasts ADD COLUMN weather_code INTEGER;
        ALTER TABLE weather_forecasts ALTER COLUMN issued_at DROP NOT NULL;
        ALTER TABLE weather_forecasts ALTER COLUMN nx DROP NOT NULL;
        ALTER TABLE weather_forecasts ALTER COLUMN ny DROP NOT NULL;
        ALTER TABLE solar_times ADD COLUMN provider TEXT NOT NULL DEFAULT 'kasi';
    """)


def downgrade() -> None:
    # Refuse a lossy downgrade if non-KMA rows exist; never fabricate grid/issue data.
    op.execute("""
        ALTER TABLE weather_forecasts ALTER COLUMN issued_at SET NOT NULL;
        ALTER TABLE weather_forecasts ALTER COLUMN nx SET NOT NULL;
        ALTER TABLE weather_forecasts ALTER COLUMN ny SET NOT NULL;
        ALTER TABLE weather_forecasts DROP COLUMN weather_code;
        ALTER TABLE weather_forecasts DROP COLUMN provider;
        ALTER TABLE solar_times DROP COLUMN provider;
    """)
