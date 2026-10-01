"""Keep unfiltered OSM highway geometry separate from pedestrian routing."""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE osm_display_roads (
            osm_way_id bigint PRIMARY KEY,
            tags jsonb NOT NULL,
            geom geometry(LineString, 5179) NOT NULL,
            snapshot_at timestamptz NOT NULL
        );
        CREATE INDEX osm_display_roads_geom_idx ON osm_display_roads USING gist (geom);
    """)


def downgrade():
    op.drop_table("osm_display_roads")
