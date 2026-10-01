"""Read-only screening of demo place coordinates against the loaded OSM network.

This measures map-data proximity, not a verified pedestrian entrance or walkability.
"""

import argparse
import json
from collections import Counter
from datetime import time

from psycopg.rows import dict_row

from app.db.connection import connect_database
from app.repositories.place_repository import find_place
from app.services.route_service import (
    RouteNotFoundError, RoutingDataNotFoundError, SnapDistanceExceededError,
    get_shortest_route, prepare_route,
)
from app.services.weather_service import RouteTimeContext


DEFAULT_NAMES = (
    "도화역", "수봉공원", "주안역", "인천사랑병원", "수봉도서관", "더나눔병원",
)
REVIEW_SNAP_M = 50
DEFAULT_PAIRS = (
    ("도화역", "수봉공원"),
    ("주안역", "인천사랑병원"),
    ("도화역", "수봉도서관"),
)


def audit_route_pairs(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, object]]:
    """Check graph reachability and returned metric coverage without selection writes."""
    results = []
    context = RouteTimeContext(time(14), False, "audit")
    for start, end in pairs:
        origin, destination = find_place(start), find_place(end)
        if origin is None or destination is None:
            results.append({"start": start, "end": end, "error": "place_not_found"})
            continue
        coordinates = {
            "start_longitude": origin["longitude"],
            "start_latitude": origin["latitude"],
            "end_longitude": destination["longitude"],
            "end_latitude": destination["latitude"],
            "source": "osm",
        }
        try:
            prepared = prepare_route(**coordinates)
            route = get_shortest_route(**coordinates, prepared=prepared, time_context=context)
        except (RouteNotFoundError, RoutingDataNotFoundError, SnapDistanceExceededError) as exc:
            results.append({"start": start, "end": end, "error": type(exc).__name__})
            continue
        properties = route["properties"]
        results.append({
            "start": start,
            "end": end,
            "distance_m": properties["total_distance_m"],
            "snap_m": [properties["start_snap_distance_m"], properties["end_snap_distance_m"]],
            "centreline_fallback_distance_m": properties["centreline_fallback_distance_m"],
            "unverified_major_road_count": properties["unverified_major_road_count"],
            "crossing_data_available": properties["crossing_data_available"],
        })
    return results


def audit_places(names: tuple[str, ...]) -> dict[str, object]:
    with connect_database() as connection:
        connection.read_only = True
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT p.name, p.category, p.source,
                       ST_X(ST_Transform(p.geom, 4326)) AS longitude,
                       ST_Y(ST_Transform(p.geom, 4326)) AS latitude,
                       ST_Distance(p.geom, road.geom) AS nearest_road_m,
                       road.source_id AS road_source_id,
                       road.properties->'osm_pedestrian'->>'version' AS pedestrian_version,
                       road.properties->'osm_pedestrian'->>'centreline_fallback' AS centreline_fallback
                FROM places p
                LEFT JOIN LATERAL (
                    SELECT r.geom, r.source_id, r.properties
                    FROM road_segments r
                    WHERE r.source = 'osm' AND ST_DWithin(r.geom, p.geom, 500)
                    ORDER BY r.geom <-> p.geom
                    LIMIT 1
                ) road ON true
                WHERE p.name = ANY(%s)
                ORDER BY p.name, p.source
                """,
                (list(names),),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT count(*) AS osm_edges,
                       count(*) FILTER (WHERE properties->'osm_pedestrian'->>'version' IS NOT NULL)
                           AS pedestrian_tagged_edges,
                       count(*) FILTER (WHERE properties->'osm_pedestrian'->>'centreline_fallback' = 'true')
                           AS centreline_fallback_edges,
                       count(*) FILTER (WHERE properties->'osm_pedestrian'->>'is_crossing' = 'true')
                           AS crossing_edges
                FROM road_segments WHERE source = 'osm'
                """
            )
            network = dict(cursor.fetchone())
            cursor.execute("SELECT to_regclass('public_crosswalks')")
            if cursor.fetchone()["to_regclass"] is not None:
                cursor.execute("SELECT count(*) AS count FROM public_crosswalks")
                network["official_crosswalk_points"] = cursor.fetchone()["count"]
            else:
                network["official_crosswalk_points"] = None

    counts = Counter(row["name"] for row in rows)
    results = []
    for name in names:
        matches = [row for row in rows if row["name"] == name]
        if not matches:
            results.append({"name": name, "issues": ["not_in_local_places"]})
            continue
        for row in matches:
            distance = row["nearest_road_m"]
            issues = []
            if counts[name] > 1:
                issues.append("same_name_multiple_records")
            if row["source"] == "demo-landmark":
                issues.append("demo_coordinate_requires_entrance_verification")
            if distance is None:
                issues.append("no_osm_road_within_500m")
            elif distance > REVIEW_SNAP_M:
                issues.append("nearest_road_over_50m_review")
            if row["pedestrian_version"] is None:
                issues.append("nearest_road_without_pedestrian_metadata")
            if row["centreline_fallback"] == "true":
                issues.append("nearest_road_is_centreline_fallback")
            results.append({
                "name": name,
                "category": row["category"],
                "source": row["source"],
                "longitude": round(row["longitude"], 6),
                "latitude": round(row["latitude"], 6),
                "nearest_road_m": round(distance, 1) if distance is not None else None,
                "road_source_id": row["road_source_id"],
                "issues": issues,
            })
    return {
        "note": "OSM proximity is not evidence of an entrance, legal crossing, or field-verified walkability.",
        "network": network,
        "places": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="Exact local place names")
    parser.add_argument("--check-routes", action="store_true", help="Also test three demo pairs on the OSM graph")
    args = parser.parse_args()
    result = audit_places(tuple(args.names) or DEFAULT_NAMES)
    if args.check_routes:
        result["routes"] = audit_route_pairs(DEFAULT_PAIRS)
    print(json.dumps(result, ensure_ascii=False, indent=2))
