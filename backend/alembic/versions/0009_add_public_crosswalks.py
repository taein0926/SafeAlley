"""Add official crosswalk POIs as independent reference data.

Revision ID: 0009
Revises: 0008
"""

from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public_crosswalks (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            source_id VARCHAR(128) NOT NULL,
            source_dataset TEXT NOT NULL,
            source_url TEXT NOT NULL,
            reference_date DATE NOT NULL,
            geom geometry(Point, 5179) NOT NULL,
            UNIQUE (source, source_id)
        );
        CREATE INDEX ix_public_crosswalks_geom ON public_crosswalks USING GIST (geom);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE public_crosswalks")
