"""Create streetlight and derived road safety analysis tables.

Revision ID: 0004
Revises: 0003
"""

from alembic import op


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE streetlights (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            source_id VARCHAR(128) NOT NULL,
            pole_name VARCHAR(255),
            cabinet_name VARCHAR(255),
            label_no VARCHAR(255),
            longitude DOUBLE PRECISION NOT NULL
                CHECK (longitude BETWEEN -180 AND 180),
            latitude DOUBLE PRECISION NOT NULL
                CHECK (latitude BETWEEN -90 AND 90),
            geom geometry(Point, 5179) NOT NULL,
            matched_road_id BIGINT REFERENCES road_segments(id)
                ON DELETE SET NULL,
            matched_road_distance_m DOUBLE PRECISION
                CHECK (
                    matched_road_distance_m IS NULL
                    OR matched_road_distance_m >= 0
                ),
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_streetlights_source UNIQUE (source, source_id),
            CONSTRAINT ck_streetlights_srid CHECK (ST_SRID(geom) = 5179),
            CONSTRAINT ck_streetlights_geometry_type
                CHECK (ST_GeometryType(geom) = 'ST_Point')
        );

        CREATE INDEX ix_streetlights_geom_gist
            ON streetlights USING GIST (geom);
        CREATE INDEX ix_streetlights_matched_road
            ON streetlights (matched_road_id);
        CREATE INDEX ix_streetlights_source
            ON streetlights (source);

        CREATE TABLE road_safety_segments (
            id BIGSERIAL PRIMARY KEY,
            road_id BIGINT NOT NULL REFERENCES road_segments(id)
                ON DELETE CASCADE,
            segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
            length_m DOUBLE PRECISION NOT NULL CHECK (length_m > 0),
            geom geometry(LineString, 5179) NOT NULL,
            nearest_light_distance_m DOUBLE PRECISION NOT NULL
                CHECK (nearest_light_distance_m >= 0),
            nearby_light_count INTEGER NOT NULL
                CHECK (nearby_light_count >= 0),
            light_density DOUBLE PRECISION NOT NULL
                CHECK (light_density >= 0),
            dark_gap_proxy_m DOUBLE PRECISION NOT NULL
                CHECK (dark_gap_proxy_m >= 0),
            distance_score NUMERIC(5, 2) NOT NULL
                CHECK (distance_score BETWEEN 0 AND 100),
            density_score NUMERIC(5, 2) NOT NULL
                CHECK (density_score BETWEEN 0 AND 100),
            gap_score NUMERIC(5, 2) NOT NULL
                CHECK (gap_score BETWEEN 0 AND 100),
            safety_score NUMERIC(5, 2) NOT NULL
                CHECK (safety_score BETWEEN 0 AND 100),
            analysis_version VARCHAR(64) NOT NULL,
            analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_road_safety_segment UNIQUE (road_id, segment_index),
            CONSTRAINT ck_road_safety_segments_srid
                CHECK (ST_SRID(geom) = 5179),
            CONSTRAINT ck_road_safety_segments_geometry_type
                CHECK (ST_GeometryType(geom) = 'ST_LineString')
        );

        CREATE INDEX ix_road_safety_segments_geom_gist
            ON road_safety_segments USING GIST (geom);
        CREATE INDEX ix_road_safety_segments_road
            ON road_safety_segments (road_id);
        CREATE INDEX ix_road_safety_segments_score
            ON road_safety_segments (safety_score);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS road_safety_segments;
        DROP TABLE IF EXISTS streetlights;
        """
    )
