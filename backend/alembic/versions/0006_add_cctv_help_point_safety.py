"""Add CCTV, help point, and composite safety analysis fields.

Revision ID: 0006
Revises: 0005
"""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cctvs (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            source_id VARCHAR(160) NOT NULL,
            management_agency VARCHAR(255),
            road_address TEXT,
            parcel_address TEXT,
            purpose VARCHAR(255),
            camera_count INTEGER,
            camera_pixels DOUBLE PRECISION,
            direction_info TEXT,
            retention_days INTEGER,
            installed_at VARCHAR(32),
            agency_phone VARCHAR(64),
            longitude DOUBLE PRECISION,
            latitude DOUBLE PRECISION,
            geom geometry(Point, 5179),
            data_reference_date VARCHAR(32),
            is_safety_cctv BOOLEAN NOT NULL DEFAULT FALSE,
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_cctvs_source UNIQUE (source, source_id),
            CONSTRAINT ck_cctvs_longitude CHECK (
                longitude IS NULL OR longitude BETWEEN -180 AND 180
            ),
            CONSTRAINT ck_cctvs_latitude CHECK (
                latitude IS NULL OR latitude BETWEEN -90 AND 90
            ),
            CONSTRAINT ck_cctvs_srid CHECK (
                geom IS NULL OR ST_SRID(geom) = 5179
            ),
            CONSTRAINT ck_cctvs_geometry_type CHECK (
                geom IS NULL OR ST_GeometryType(geom) = 'ST_Point'
            )
        );

        CREATE INDEX ix_cctvs_geom_gist ON cctvs USING GIST (geom);
        CREATE INDEX ix_cctvs_source ON cctvs (source);
        CREATE INDEX ix_cctvs_safety ON cctvs (is_safety_cctv)
            WHERE is_safety_cctv AND geom IS NOT NULL;

        CREATE TABLE help_points (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            name VARCHAR(500),
            category VARCHAR(64),
            subtype VARCHAR(255),
            address TEXT,
            phone VARCHAR(128),
            emergency_phone VARCHAR(128),
            coordinate_quality VARCHAR(128),
            coordinate_status VARCHAR(128),
            coordinate_source VARCHAR(255),
            source_org VARCHAR(255),
            source_dataset VARCHAR(500),
            reference_date VARCHAR(64),
            geom geometry(Point, 5179) NOT NULL,
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_help_points_source UNIQUE (source, external_id),
            CONSTRAINT ck_help_points_srid CHECK (ST_SRID(geom) = 5179),
            CONSTRAINT ck_help_points_geometry_type CHECK (
                ST_GeometryType(geom) = 'ST_Point'
            )
        );

        CREATE INDEX ix_help_points_geom_gist
            ON help_points USING GIST (geom);
        CREATE INDEX ix_help_points_source_category
            ON help_points (source, category);

        ALTER TABLE road_safety_segments
            ADD COLUMN streetlight_score NUMERIC(5, 2) NOT NULL DEFAULT 0
                CHECK (streetlight_score BETWEEN 0 AND 100),
            ADD COLUMN nearest_cctv_distance_m DOUBLE PRECISION,
            ADD COLUMN nearby_cctv_count INTEGER,
            ADD COLUMN cctv_density DOUBLE PRECISION,
            ADD COLUMN cctv_gap_proxy_m DOUBLE PRECISION,
            ADD COLUMN cctv_distance_score NUMERIC(5, 2),
            ADD COLUMN cctv_density_score NUMERIC(5, 2),
            ADD COLUMN cctv_gap_score NUMERIC(5, 2),
            ADD COLUMN cctv_score NUMERIC(5, 2),
            ADD COLUMN nearest_help_point_distance_m DOUBLE PRECISION,
            ADD COLUMN nearest_help_point_id BIGINT REFERENCES help_points(id)
                ON DELETE SET NULL,
            ADD COLUMN nearest_help_point_category VARCHAR(64),
            ADD COLUMN nearest_police_distance_m DOUBLE PRECISION,
            ADD COLUMN nearest_fire_station_distance_m DOUBLE PRECISION,
            ADD COLUMN nearest_emergency_medical_distance_m DOUBLE PRECISION,
            ADD COLUMN help_point_score NUMERIC(5, 2);

        UPDATE road_safety_segments
        SET streetlight_score = safety_score;

        ALTER TABLE road_safety_segments
            ADD CONSTRAINT ck_road_safety_cctv_metrics CHECK (
                (nearest_cctv_distance_m IS NULL OR nearest_cctv_distance_m >= 0)
                AND (nearby_cctv_count IS NULL OR nearby_cctv_count >= 0)
                AND (cctv_density IS NULL OR cctv_density >= 0)
                AND (cctv_gap_proxy_m IS NULL OR cctv_gap_proxy_m >= 0)
            ),
            ADD CONSTRAINT ck_road_safety_component_scores CHECK (
                (cctv_distance_score IS NULL OR cctv_distance_score BETWEEN 0 AND 100)
                AND (cctv_density_score IS NULL OR cctv_density_score BETWEEN 0 AND 100)
                AND (cctv_gap_score IS NULL OR cctv_gap_score BETWEEN 0 AND 100)
                AND (cctv_score IS NULL OR cctv_score BETWEEN 0 AND 100)
                AND (help_point_score IS NULL OR help_point_score BETWEEN 0 AND 100)
            );

        ALTER TABLE road_segments
            ADD COLUMN help_point_score NUMERIC(5, 2) NOT NULL DEFAULT 0
                CHECK (help_point_score BETWEEN 0 AND 100);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE road_segments DROP COLUMN IF EXISTS help_point_score;
        ALTER TABLE road_safety_segments
            DROP COLUMN IF EXISTS help_point_score,
            DROP COLUMN IF EXISTS nearest_emergency_medical_distance_m,
            DROP COLUMN IF EXISTS nearest_fire_station_distance_m,
            DROP COLUMN IF EXISTS nearest_police_distance_m,
            DROP COLUMN IF EXISTS nearest_help_point_category,
            DROP COLUMN IF EXISTS nearest_help_point_id,
            DROP COLUMN IF EXISTS nearest_help_point_distance_m,
            DROP COLUMN IF EXISTS cctv_score,
            DROP COLUMN IF EXISTS cctv_gap_score,
            DROP COLUMN IF EXISTS cctv_density_score,
            DROP COLUMN IF EXISTS cctv_distance_score,
            DROP COLUMN IF EXISTS cctv_gap_proxy_m,
            DROP COLUMN IF EXISTS cctv_density,
            DROP COLUMN IF EXISTS nearby_cctv_count,
            DROP COLUMN IF EXISTS nearest_cctv_distance_m,
            DROP COLUMN IF EXISTS streetlight_score;
        DROP TABLE IF EXISTS cctvs;
        DROP TABLE IF EXISTS help_points;
        """
    )
