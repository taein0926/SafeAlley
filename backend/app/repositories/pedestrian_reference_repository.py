import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


class PedestrianReferenceError(RuntimeError):
    """Reference data could not be read."""


def list_pedestrian_bridges() -> list[dict]:
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
                    ORDER BY p.id
                """)
                return cursor.fetchall()
    except psycopg.Error as exc:
        raise PedestrianReferenceError("Failed to read pedestrian bridges") from exc
