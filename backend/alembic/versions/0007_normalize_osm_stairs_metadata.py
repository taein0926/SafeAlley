"""Normalize OSM stairs metadata in road segment properties.

Revision ID: 0007
Revises: 0006
"""

from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE road_segments
        SET properties = properties || jsonb_build_object(
            'highway', properties->>'highway',
            'is_steps', COALESCE(properties->>'highway' = 'steps', FALSE),
            'step_count', COALESCE(
                properties->>'step_count', properties->'osm_tags'->>'step_count'
            ),
            'incline', COALESCE(
                properties->>'incline', properties->'osm_tags'->>'incline'
            ),
            'ramp', COALESCE(
                properties->>'ramp', properties->'osm_tags'->>'ramp'
            ),
            'wheelchair', COALESCE(
                properties->>'wheelchair', properties->'osm_tags'->>'wheelchair'
            ),
            'handrail', COALESCE(
                properties->>'handrail', properties->'osm_tags'->>'handrail'
            )
        ),
        updated_at = NOW()
        WHERE source = 'osm'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE road_segments
        SET properties = properties
            - 'is_steps'
            - 'step_count'
            - 'incline'
            - 'ramp'
            - 'wheelchair'
            - 'handrail',
            updated_at = NOW()
        WHERE source = 'osm'
        """
    )
