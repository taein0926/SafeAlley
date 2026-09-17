"""Create the buildings spatial table.

Revision ID: 0003
Revises: 0002
"""

from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE buildings (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(32) NOT NULL,
            building_id VARCHAR(128) NOT NULL,
            building_name VARCHAR(255),
            address TEXT,
            main_use VARCHAR(255),
            building_area DOUBLE PRECISION
                CHECK (building_area IS NULL OR building_area >= 0),
            total_floor_area DOUBLE PRECISION
                CHECK (total_floor_area IS NULL OR total_floor_area >= 0),
            height_m DOUBLE PRECISION
                CHECK (height_m IS NULL OR height_m >= 0),
            floors INTEGER CHECK (floors IS NULL OR floors >= 0),
            source_updated_at TEXT,
            geom geometry(MultiPolygon, 5179) NOT NULL,
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_buildings_source UNIQUE (source, building_id),
            CONSTRAINT ck_buildings_srid CHECK (ST_SRID(geom) = 5179),
            CONSTRAINT ck_buildings_geometry_type
                CHECK (ST_GeometryType(geom) = 'ST_MultiPolygon')
        );

        CREATE INDEX ix_buildings_geom_gist
            ON buildings USING GIST (geom);
        CREATE INDEX ix_buildings_source
            ON buildings (source);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS buildings;")

