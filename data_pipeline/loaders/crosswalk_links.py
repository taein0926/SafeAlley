"""Attach official POI provenance only to OSM-tagged crossing edges.

This does not turn a nearby road into a walkable crossing or change route counts.
"""

from collections import defaultdict

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection


MATCH_RADIUS_M = 8.0


def link_public_crosswalks() -> dict[str, int | float]:
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.source_id, r.source_id, ST_Distance(c.geom, r.crossing_geom)
                FROM public_crosswalks c
                CROSS JOIN LATERAL (
                    SELECT source_id, crossing_geom
                    FROM (
                        SELECT source_id,
                            CASE
                                WHEN properties->'osm_tags'->>'footway' = 'crossing'
                                    THEN geom
                                WHEN properties->'crossing_node_ids' @> jsonb_build_array(source_node_id)
                                 AND properties->'crossing_node_ids' @> jsonb_build_array(target_node_id)
                                    THEN ST_Collect(ST_StartPoint(geom), ST_EndPoint(geom))
                                WHEN properties->'crossing_node_ids' @> jsonb_build_array(source_node_id)
                                    THEN ST_StartPoint(geom)
                                WHEN properties->'crossing_node_ids' @> jsonb_build_array(target_node_id)
                                    THEN ST_EndPoint(geom)
                            END AS crossing_geom
                        FROM road_segments
                        WHERE source = 'osm'
                          AND geom && ST_Expand(c.geom, %s)
                          AND jsonb_array_length(
                              COALESCE(properties->'crossing_node_ids', '[]'::jsonb)
                          ) > 0
                    ) mapped
                    WHERE crossing_geom IS NOT NULL
                      AND ST_DWithin(crossing_geom, c.geom, %s)
                    ORDER BY crossing_geom <-> c.geom, source_id
                    LIMIT 1
                ) r
                WHERE c.source = 'incheon-road-poi-2022'
                ORDER BY c.source_id
            """, (MATCH_RADIUS_M, MATCH_RADIUS_M))
            matches = cursor.fetchall()
            by_road: dict[str, list[str]] = defaultdict(list)
            for public_id, road_id, _distance in matches:
                by_road[road_id].append(public_id)
            cursor.execute("""
                UPDATE road_segments
                SET properties = properties - 'official_crosswalk_source_ids'
                WHERE source = 'osm'
                  AND properties ? 'official_crosswalk_source_ids'
            """)
            for road_id, public_ids in by_road.items():
                cursor.execute("""
                    UPDATE road_segments
                    SET properties = jsonb_set(
                        properties, '{official_crosswalk_source_ids}', %s, true
                    )
                    WHERE source = 'osm' AND source_id = %s
                """, (Jsonb(sorted(public_ids)), road_id))
            cursor.execute("""
                SELECT count(*) FROM public_crosswalks
                WHERE source = 'incheon-road-poi-2022'
            """)
            total = cursor.fetchone()[0]
    return {"official_points": total, "matched_points": len(matches),
            "unmatched_points": total - len(matches),
            "matched_osm_edges": len(by_road), "match_radius_m": MATCH_RADIUS_M}
