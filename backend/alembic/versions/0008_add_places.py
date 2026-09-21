"""Add the local place-name index used by natural-language routing.

Revision ID: 0008
Revises: 0007
"""

from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE places (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            source_id VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            aliases TEXT[] NOT NULL DEFAULT '{}',
            category VARCHAR(64),
            address TEXT,
            geom geometry(Point, 5179) NOT NULL,
            CONSTRAINT uq_places_source_id UNIQUE (source, source_id)
        );

        CREATE INDEX ix_places_geom ON places USING GIST (geom);
        CREATE INDEX ix_places_name_normalized
            ON places ((lower(regexp_replace(name, '\\s+', '', 'g'))));

        INSERT INTO places (source, source_id, name, aliases, category, address, geom)
        VALUES (
            'demo-landmark', 'juan-station', '주안역',
            ARRAY['주안역 1호선', '주안역 인천2호선'], 'subway_station',
            '인천광역시 미추홀구 주안동',
            ST_Transform(ST_SetSRID(ST_MakePoint(126.6804, 37.4649), 4326), 5179)
        );

        INSERT INTO places (source, source_id, name, aliases, category, address, geom)
        SELECT
            'help-point', id::text, name, ARRAY[]::text[], category, address, geom
        FROM help_points
        WHERE name IS NOT NULL
        ON CONFLICT (source, source_id) DO NOTHING;

        UPDATE places
        SET aliases = ARRAY['사랑병원']
        WHERE source = 'help-point' AND name = '인천사랑병원';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS places;")
