"""Export official crosswalk points near demo paths for manual network review.

Proximity is evidence to inspect, not permission to create a crossing edge.
"""

import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform
from shapely.strtree import STRtree


ROUTE_REVIEW_RADIUS_M = 25.0
OSM_CROSSING_MATCH_RADIUS_M = 8.0


def audit_route_crosswalks(
    roads: list[dict[str, object]],
    case_routes: dict[str, list[tuple[dict[str, object], dict[str, object]]]],
    crosswalks_path: Path,
    output_path: Path,
) -> dict[str, int | str]:
    crosswalks = json.loads(crosswalks_path.read_text(encoding="utf-8"))
    if crosswalks.get("type") != "FeatureCollection":
        raise ValueError("Official crosswalk input must be a GeoJSON FeatureCollection")
    project = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform

    mapped_shapes = []
    mapped_source_ids = []
    for road in roads:
        properties = road["properties"]
        crossing_ids = properties.get("crossing_node_ids") or []
        if not crossing_ids:
            continue
        coordinates = road["geometry"]["coordinates"]
        source_id = str(properties["source_id"])
        # A crossing way is mapped over its length; a crossing node is only
        # mapped at its actual endpoint, not anywhere on a long road segment.
        if any(int(value) < 0 for value in crossing_ids):
            mapped_shapes.append(transform(project, LineString(coordinates)))
            mapped_source_ids.append(source_id)
        for node_id, coordinate in (
            (properties["source_node_id"], coordinates[0]),
            (properties["target_node_id"], coordinates[-1]),
        ):
            if int(node_id) in crossing_ids:
                mapped_shapes.append(transform(project, Point(coordinate)))
                mapped_source_ids.append(source_id)
    mapped_tree = STRtree(mapped_shapes) if mapped_shapes else None

    route_indexes = {}
    for name, edges in case_routes.items():
        lines = [
            transform(project, LineString(geometry["coordinates"]))
            for _, geometry in edges
        ]
        if lines:
            route_indexes[name] = (
                STRtree(lines),
                {str(properties["source_id"]) for properties, _ in edges},
            )

    candidates = []
    status_counts = {
        "mapped_on_route": 0,
        "mapped_near_route": 0,
        "needs_connection_review": 0,
    }
    for crosswalk in crosswalks["features"]:
        point = transform(project, Point(crosswalk["geometry"]["coordinates"]))
        nearby_routes = []
        route_source_ids = set()
        nearest_route_distance_m = float("inf")
        for name, (route_tree, source_ids) in route_indexes.items():
            route_distance = point.distance(route_tree.geometries[int(route_tree.nearest(point))])
            if route_distance <= ROUTE_REVIEW_RADIUS_M:
                nearby_routes.append(name)
                route_source_ids.update(source_ids)
                nearest_route_distance_m = min(nearest_route_distance_m, route_distance)
        if not nearby_routes:
            continue

        mapped_id = None
        mapped_distance = None
        if mapped_tree is not None:
            index = int(mapped_tree.nearest(point))
            mapped_distance = point.distance(mapped_shapes[index])
            if mapped_distance <= OSM_CROSSING_MATCH_RADIUS_M:
                mapped_id = mapped_source_ids[index]

        if mapped_id in route_source_ids:
            status = "mapped_on_route"
        elif mapped_id is not None:
            status = "mapped_near_route"
        else:
            status = "needs_connection_review"
        status_counts[status] += 1
        candidates.append({
            "type": "Feature",
            "geometry": crosswalk["geometry"],
            "properties": {
                "source_id": crosswalk["properties"]["source_id"],
                "affected_routes": nearby_routes,
                "nearest_route_distance_m": round(nearest_route_distance_m, 1),
                "nearest_mapped_crossing_distance_m": (
                    round(mapped_distance, 1) if mapped_distance is not None else None
                ),
                "nearest_mapped_crossing_source_id": mapped_id,
                "network_review_status": status,
                "field_status": "unverified",
                "check_legal_crossing": None,
                "check_sidewalk_connection": None,
                "check_kerb_and_barrier": None,
                "evidence_photo_ref": None,
                "reviewer": None,
                "reviewed_at": None,
            },
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {
            "purpose": "Manual review of official crosswalk POIs near demo routes",
            "source": crosswalks.get("metadata", {}).get("source"),
            "reference_date": crosswalks.get("metadata", {}).get("reference_date"),
            "crs": "EPSG:4326",
            "route_review_radius_m": ROUTE_REVIEW_RADIUS_M,
            "osm_crossing_match_radius_m": OSM_CROSSING_MATCH_RADIUS_M,
            "warning": "Proximity does not prove a legal crossing or graph connection; no route edges were changed",
        },
        "features": candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "crosswalk_review_candidates": len(candidates),
        **status_counts,
        "crosswalk_audit_path": str(output_path),
    }
