"""Offline pedestrian-network audit using actual processed OSM edges."""

import json
from heapq import heappop, heappush
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from analysis.crosswalk_quality import audit_route_crosswalks


def _distance_m(a: list[float], b: list[float]) -> float:
    lon1, lat1 = map(radians, a)
    lon2, lat2 = map(radians, b)
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 12_742_017.6 * asin(sqrt(h))


def audit_road_network(
    roads_path: Path,
    cases_path: Path,
    field_audit_path: Path | None = None,
    crosswalks_path: Path | None = None,
    crosswalk_audit_path: Path | None = None,
) -> dict[str, object]:
    roads = json.loads(roads_path.read_text(encoding="utf-8"))["features"]
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    positions: dict[int, list[float]] = {}
    adjacency: dict[int, list[tuple[int, dict[str, object], float, dict[str, object]]]] = {}
    reviewed_adjacency: dict[int, list[tuple[int, dict[str, object], float, dict[str, object]]]] = {}
    for road in roads:
        p = road["properties"]
        a, b = int(p["source_node_id"]), int(p["target_node_id"])
        start, end = road["geometry"]["coordinates"][:2]
        positions[a], positions[b] = start, end
        length = _distance_m(start, end)
        factor = float(p.get("walkability_factor", 1))
        usable_without_fallback = (
            p.get("walkability_class") != "major_road_fallback"
            or p.get("field_status") == "verified_walkable"
        )
        if p.get("forward_allowed", True):
            edge = (b, p, length * factor, road["geometry"])
            adjacency.setdefault(a, []).append(edge)
            if usable_without_fallback:
                reviewed_adjacency.setdefault(a, []).append(edge)
        if p.get("reverse_allowed", True):
            edge = (a, p, length * factor, road["geometry"])
            adjacency.setdefault(b, []).append(edge)
            if usable_without_fallback:
                reviewed_adjacency.setdefault(b, []).append(edge)

    def snap(point: list[float], nodes: set[int] | None = None) -> tuple[int, float]:
        return min(
            ((node, _distance_m(point, location)) for node, location in positions.items()
             if nodes is None or node in nodes),
            key=lambda item: item[1],
        )

    def trace_route(
        start: int,
        goal: int,
        graph: dict[int, list[tuple[int, dict[str, object], float, dict[str, object]]]],
    ) -> tuple[list[tuple[int, int, dict[str, object], dict[str, object]]], bool]:
        frontier = [(0.0, start)]
        best = {start: 0.0}
        previous: dict[int, tuple[int, dict[str, object], dict[str, object]]] = {}
        while frontier:
            cost, node = heappop(frontier)
            if cost > best.get(node, float("inf")):
                continue
            if node == goal:
                break
            for next_node, properties, edge_cost, geometry in graph.get(node, []):
                new_cost = cost + edge_cost
                if new_cost < best.get(next_node, float("inf")):
                    best[next_node] = new_cost
                    previous[next_node] = (node, properties, geometry)
                    heappush(frontier, (new_cost, next_node))
        route = []
        cursor = goal
        while cursor != start and cursor in previous:
            parent, properties, geometry = previous[cursor]
            route.append((parent, cursor, properties, geometry))
            cursor = parent
        route.reverse()
        return route, cursor == start

    results = []
    field_edges: dict[str, dict[str, object]] = {}
    case_routes: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    for case in cases:
        start, start_gap = snap(case["origin"])
        goal, goal_gap = snap(case["destination"])
        route, connected = trace_route(start, goal, adjacency)
        reviewed_nodes = set(reviewed_adjacency)
        reviewed_nodes.update(
            next_node for edges in reviewed_adjacency.values() for next_node, *_ in edges
        )
        if reviewed_nodes:
            reviewed_start, reviewed_start_gap = snap(case["origin"], reviewed_nodes)
            reviewed_goal, reviewed_end_gap = snap(case["destination"], reviewed_nodes)
            reviewed_route, reviewed_connected = trace_route(
                reviewed_start, reviewed_goal, reviewed_adjacency,
            )
        else:
            reviewed_start_gap = reviewed_end_gap = float("inf")
            reviewed_route, reviewed_connected = [], False
        if connected:
            case_routes[case["name"]] = [
                (properties, geometry) for _, _, properties, geometry in route
            ]
        forbidden = [
            edge[2]["source_id"] for edge in route
            if edge[2].get("osm_tags", {}).get("foot") in {"no", "private"}
            or edge[2].get("highway") in {"motorway", "trunk"}
        ]
        major_fallback = sum(
            1 for edge in route if edge[2].get("walkability_class") == "major_road_fallback"
        )
        if field_audit_path is not None:
            for _, _, properties, geometry in route:
                if properties.get("walkability_class") != "major_road_fallback":
                    continue
                source_id = str(properties["source_id"])
                if source_id not in field_edges:
                    field_edges[source_id] = {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": {
                            "source_id": source_id,
                            "osm_way_id": properties.get("osm_way_id"),
                            "highway": properties.get("highway"),
                            "name": properties.get("name"),
                            "affected_routes": [],
                            "field_status": "unverified",
                            "check_sidewalk_continuity": None,
                            "check_legal_crossing": None,
                            "check_steps_or_barrier": None,
                            "check_night_visibility": None,
                            "evidence_photo_ref": None,
                            "reviewer": None,
                            "reviewed_at": None,
                        },
                    }
                affected = field_edges[source_id]["properties"]["affected_routes"]
                if case["name"] not in affected:
                    affected.append(case["name"])
        result = {
            "name": case["name"],
            "connected": connected,
            "start_snap_m": round(start_gap, 1),
            "end_snap_m": round(goal_gap, 1),
            "edge_count": len(route),
            "major_road_fallback_edges": major_fallback,
            "fallback_free_connected": reviewed_connected,
            "fallback_free_start_snap_m": (
                round(reviewed_start_gap, 1) if reviewed_nodes else None
            ),
            "fallback_free_end_snap_m": (
                round(reviewed_end_gap, 1) if reviewed_nodes else None
            ),
            "fallback_free_edge_count": len(reviewed_route),
            "forbidden_edges": forbidden,
            "pass": connected and start_gap <= case.get("max_snap_m", 500)
                    and goal_gap <= case.get("max_snap_m", 500) and not forbidden,
        }
        results.append(result)
    report = {"road_edges": len(roads), "graph_nodes": len(positions),
              "cases": results, "passed": sum(item["pass"] for item in results)}
    if field_audit_path is not None:
        field_audit_path.parent.mkdir(parents=True, exist_ok=True)
        field_audit_path.write_text(json.dumps({
            "type": "FeatureCollection",
            "metadata": {
                "purpose": "On-site verification of major-road fallback edges",
                "status": "not_field_verified",
                "crs": "EPSG:4326",
            },
            "features": list(field_edges.values()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        report["field_audit_unique_edges"] = len(field_edges)
        report["field_audit_path"] = str(field_audit_path)
    if crosswalk_audit_path is not None:
        if crosswalks_path is None:
            raise ValueError("crosswalks_path is required for a crosswalk audit")
        report.update(audit_route_crosswalks(
            roads, case_routes, crosswalks_path, crosswalk_audit_path,
        ))
    return report
