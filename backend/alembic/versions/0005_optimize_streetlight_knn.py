"""Add a source-aware spatial index for streetlight KNN queries.

Revision ID: 0005
Revises: 0004
"""

from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS btree_gist;
        CREATE INDEX ix_streetlights_source_geom_gist
            ON streetlights USING GIST (source, geom);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_streetlights_source_geom_gist")
