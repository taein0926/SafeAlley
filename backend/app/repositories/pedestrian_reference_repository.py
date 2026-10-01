import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database
from app.repositories.road_repository import BoundingBox


class PedestrianReferenceError(RuntimeError):
    """Reference data could not be read."""


def list_pedestrian_bridges(bbox: BoundingBox | None = None) -> list[dict]:
    spatial_filter = ""
    parameters = []
    if bbox is not None:
        spatial_filter = " AND ST_Intersects(p.geom, ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4326),5179))"
        parameters = [bbox.min_longitude, bbox.min_latitude, bbox.max_longitude, bbox.max_latitude]
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    WITH linked AS (
                        SELECT DISTINCT jsonb_array_elements_text(
                            properties->'pedestrian_reference'->'bridge_ids'
                        ) AS reference_id
                        FROM road_segments WHERE source = 'osm'
                    )
                    SELECT p.id, p.properties,
                        ST_AsGeoJSON(ST_Transform(p.geom, 4326), 9)::json AS geometry,
                        (linked.reference_id IS NOT NULL) AS routing_connected
                    FROM pedestrian_references p
                    LEFT JOIN linked ON linked.reference_id = p.id
                    WHERE p.kind = 'bridge'
                """ + spatial_filter + """
                    ORDER BY p.id
                """, parameters)
                return cursor.fetchall()
    except psycopg.Error as exc:
        raise PedestrianReferenceError("Failed to read pedestrian bridges") from exc
