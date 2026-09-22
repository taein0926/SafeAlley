"""Keep pedestrian reference points separate from walkable topology."""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pedestrian_references (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('bridge', 'intersection')),
            properties JSONB NOT NULL,
            geom geometry(Point, 5179) NOT NULL
        );
        CREATE INDEX ix_pedestrian_references_geom
            ON pedestrian_references USING GIST (geom);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE pedestrian_references")
