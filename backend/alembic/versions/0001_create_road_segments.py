"""Create the initial road_segments spatial table.

Revision ID: 0001
Revises: None
"""

from alembic import op


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE road_segments (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(32) NOT NULL,
            source_id VARCHAR(128) NOT NULL,
            name VARCHAR(255),
            source_node_id BIGINT NOT NULL,
            target_node_id BIGINT NOT NULL,
            forward_allowed BOOLEAN NOT NULL DEFAULT TRUE,
            reverse_allowed BOOLEAN NOT NULL DEFAULT TRUE,
            geom geometry(LineString, 5179) NOT NULL,
            length_m DOUBLE PRECISION NOT NULL CHECK (length_m > 0),
            safety_score NUMERIC(5, 2) NOT NULL DEFAULT 50.0
                CHECK (safety_score BETWEEN 0 AND 100),
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_road_segments_source UNIQUE (source, source_id),
            CONSTRAINT ck_road_segments_srid CHECK (ST_SRID(geom) = 5179),
            CONSTRAINT ck_road_segments_geometry_type
                CHECK (ST_GeometryType(geom) = 'ST_LineString')
        );

        CREATE INDEX ix_road_segments_geom_gist
            ON road_segments USING GIST (geom);
        CREATE INDEX ix_road_segments_source_node
            ON road_segments (source_node_id);
        CREATE INDEX ix_road_segments_target_node
            ON road_segments (target_node_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS road_segments;")

