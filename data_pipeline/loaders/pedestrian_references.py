"""Link proximity metadata only. Never create edges, alter safety, or infer access.

Intersection buffers measure nearby ground-level exposure, NOT verified crossings.
Overlapping/duplicate buffers are unioned to avoid duplicate penalties.
Bridge provenance is attached only to existing OSM pedestrian bridge segments.
"""
from pathlib import Path

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection
from preprocess.pedestrian_references import read_pedestrian_references

INTERSECTION_RADIUS_M = 35.0
BRIDGE_MATCH_RADIUS_M = 60.0


def link_reference_metadata(cursor, reference_ids: list[str], road_source: str = "osm") -> dict:
    cursor.execute("""
        WITH refs AS (
            SELECT * FROM pedestrian_references WHERE id = ANY(%s)
        ), road_flags AS (
            SELECT r.*,
                COALESCE(properties->'osm_tags'->>'bridge', 'no') NOT IN ('no', 'false', '0', '')
                    AS bridge,
                (COALESCE(properties->'osm_tags'->>'bridge', 'no') NOT IN ('no', 'false', '0', '')
                 OR COALESCE(properties->'osm_tags'->>'tunnel', 'no') NOT IN ('no', 'false', '0', '')
                 OR COALESCE(properties->'osm_tags'->>'layer', '0') NOT IN ('0', ''))
                    AS grade_separated
            FROM road_segments r WHERE source = %s
        ), linked AS (
            SELECT r.id, jsonb_build_object(
                'version', 'pedestrian-reference-v1',
                'intersection_exposure_m', CASE WHEN r.grade_separated THEN 0
                    ELSE LEAST(r.length_m, COALESCE(i.exposure_m, 0)) END,
                'grade_separated', r.grade_separated,
                'bridge_ids', COALESCE(b.ids, '[]'::jsonb)
            ) AS metadata
            FROM road_flags r
            LEFT JOIN LATERAL (
                SELECT ST_Length(ST_Intersection(r.geom,
                    ST_UnaryUnion(ST_Collect(ST_Buffer(p.geom, %s))))) AS exposure_m
                FROM refs p
                WHERE p.kind = 'intersection' AND NOT r.grade_separated
                    AND ST_DWithin(r.geom, p.geom, %s)
            ) i ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(p.id ORDER BY p.id) AS ids FROM refs p
                WHERE p.kind = 'bridge' AND r.bridge
                    AND r.properties->>'highway' IN ('footway', 'path', 'pedestrian', 'steps')
                    AND ST_DWithin(r.geom, p.geom, %s)
            ) b ON TRUE
        )
        UPDATE road_segments r
        SET properties = jsonb_set(r.properties, '{pedestrian_reference}', linked.metadata)
        FROM linked WHERE r.id = linked.id
    """, (reference_ids, road_source, INTERSECTION_RADIUS_M, INTERSECTION_RADIUS_M, BRIDGE_MATCH_RADIUS_M))
    cursor.execute("""
        SELECT count(*) FILTER (
            WHERE (properties->'pedestrian_reference'->>'intersection_exposure_m')::float > 0),
            count(*) FILTER (
            WHERE jsonb_array_length(properties->'pedestrian_reference'->'bridge_ids') > 0),
            count(*)
        FROM road_segments WHERE source = %s
    """, (road_source,))
    intersection_edges, bridge_edges, annotated_edges = cursor.fetchone()
    cursor.execute("""
        SELECT DISTINCT jsonb_array_elements_text(
            properties->'pedestrian_reference'->'bridge_ids') AS id
        FROM road_segments WHERE source = %s ORDER BY id
    """, (road_source,))
    bridge_ids = [row[0] for row in cursor.fetchall()]
    return {"intersection_edges": intersection_edges, "bridge_edges": bridge_edges,
            "annotated_edges": annotated_edges, "matched_bridge_ids": bridge_ids,
            "intersection_radius_m": INTERSECTION_RADIUS_M, "bridge_match_radius_m": BRIDGE_MATCH_RADIUS_M}


def load_pedestrian_references(path: Path) -> dict:
    features = read_pedestrian_references(path)  # Validate everything before any DB writes.
    with database_connection() as connection:
        with connection.cursor() as cursor:
            for feature in features:
                longitude, latitude = feature["geometry"]["coordinates"]
                cursor.execute("""
                    INSERT INTO pedestrian_references (id, kind, properties, geom)
                    VALUES (%s, %s, %s, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179))
                    ON CONFLICT (id) DO UPDATE SET
                        kind = EXCLUDED.kind, properties = EXCLUDED.properties, geom = EXCLUDED.geom
                """, (feature["id"], feature["properties"]["kind"], Jsonb(feature["properties"]), longitude, latitude))
            linked = link_reference_metadata(cursor, [feature["id"] for feature in features])
    return {"references": len(features),
            "intersections": sum(f["properties"]["kind"] == "intersection" for f in features),
            "bridges": sum(f["properties"]["kind"] == "bridge" for f in features), **linked}
