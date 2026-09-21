"""Add CCTV coordinate provenance and quality.

Revision ID: 0010
Revises: 0009
"""

from alembic import op


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cctvs
            ADD COLUMN coordinate_quality VARCHAR(32) NOT NULL DEFAULT 'unknown',
            ADD COLUMN coordinate_source VARCHAR(64) NOT NULL DEFAULT 'official_source',
            ADD COLUMN longitude_precision_digits SMALLINT,
            ADD COLUMN latitude_precision_digits SMALLINT;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cctvs
            DROP COLUMN latitude_precision_digits,
            DROP COLUMN longitude_precision_digits,
            DROP COLUMN coordinate_source,
            DROP COLUMN coordinate_quality;
        """
    )
