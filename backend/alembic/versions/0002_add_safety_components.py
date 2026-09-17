"""Add normalized safety component scores to road segments.

Revision ID: 0002
Revises: 0001
"""

from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE road_segments
            ADD COLUMN streetlight_score NUMERIC(5, 2) NOT NULL DEFAULT 50.0
                CHECK (streetlight_score BETWEEN 0 AND 100),
            ADD COLUMN cctv_score NUMERIC(5, 2) NOT NULL DEFAULT 50.0
                CHECK (cctv_score BETWEEN 0 AND 100),
            ADD COLUMN population_score NUMERIC(5, 2) NOT NULL DEFAULT 50.0
                CHECK (population_score BETWEEN 0 AND 100);

        UPDATE road_segments
        SET
            streetlight_score = safety_score,
            cctv_score = safety_score,
            population_score = safety_score;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE road_segments
            DROP COLUMN population_score,
            DROP COLUMN cctv_score,
            DROP COLUMN streetlight_score;
        """
    )
