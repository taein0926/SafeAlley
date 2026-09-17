from collections.abc import Callable
from typing import Literal

from app.core.config import get_settings
from app.repositories.road_repository import (
    NearestRoadNode,
    RoutingRoadSegment,
    find_nearest_road_node,
    list_routing_road_segments,
)

from app.services.routing.astar import PathNotFoundError, PathResult, find_path
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.routing.safety_cost import SafetyCostPolicy


class RoutingDataNotFoundError(RuntimeError):
    """Raised when the database has no usable road graph."""


class SnapDistanceExceededError(RuntimeError):
    """Raised when a requested point is too far from the road graph."""


class RouteNotFoundError(RuntimeError):
    """Raised when the snapped graph nodes are disconnected."""


def _build_graph(segments: list[RoutingRoadSegment]) -> RoadGraph:
    graph = RoadGraph()

    for segment in segments:
        graph.add_node(
            GraphNode(
                id=segment.source_node_id,
                x=segment.source_x,
                y=segment.source_y,
            )
        )
        graph.add_node(
            GraphNode(
                id=segment.target_node_id,
                x=segment.target_x,
                y=segment.target_y,
            )
        )

        if segment.forward_allowed:
            graph.add_edge(
                GraphEdge(
                    segment_id=segment.id,
                    source_id=segment.source_id,
                    name=segment.name,
                    from_node_id=segment.source_node_id,
                    to_node_id=segment.target_node_id,
                    distance_m=segment.length_m,
                    streetlight_score=segment.streetlight_score,
                    cctv_score=segment.cctv_score,
                    population_score=segment.population_score,
                    safety_score=segment.safety_score,
                    coordinates=segment.coordinates,
                )
            )
        if segment.reverse_allowed:
            graph.add_edge(
                GraphEdge(
                    segment_id=segment.id,
                    source_id=segment.source_id,
                    name=segment.name,
                    from_node_id=segment.target_node_id,
                    to_node_id=segment.source_node_id,
                    distance_m=segment.length_m,
                    streetlight_score=segment.streetlight_score,
                    cctv_score=segment.cctv_score,
                    population_score=segment.population_score,
                    safety_score=segment.safety_score,
                    coordinates=tuple(reversed(segment.coordinates)),
                )
            )

    return graph


def _validate_snap_distance(node: NearestRoadNode, point_name: str) -> None:
    maximum = get_settings().route_snap_max_distance_m
    if node.distance_m > maximum:
        raise SnapDistanceExceededError(
            f"{point_name} is {node.distance_m:.1f} m from the road graph; "
            f"maximum is {maximum:.1f} m"
        )


def _merge_path_coordinates(
    edges: tuple[GraphEdge, ...],
    start_node: NearestRoadNode,
) -> list[list[float]]:
    if not edges:
        point = [start_node.longitude, start_node.latitude]
        return [point, point.copy()]

    coordinates: list[list[float]] = []
    for edge in edges:
        for coordinate in edge.coordinates:
            point = [coordinate[0], coordinate[1]]
            if not coordinates or coordinates[-1] != point:
                coordinates.append(point)
    return coordinates


def _average_safety_score(result: PathResult) -> float | None:
    if result.total_distance_m == 0:
        return None
    weighted_total = sum(
        edge.safety_score * edge.distance_m for edge in result.edges
    )
    return weighted_total / result.total_distance_m


def _route_feature(
    result: PathResult,
    start_node: NearestRoadNode,
    end_node: NearestRoadNode,
    route_type: Literal["shortest", "safe"],
    policy: SafetyCostPolicy,
) -> dict[str, object]:
    average_safety_score = _average_safety_score(result)
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": _merge_path_coordinates(result.edges, start_node),
        },
        "properties": {
            "route_type": route_type,
            "crs": "EPSG:4326",
            "total_distance": round(result.total_distance_m, 2),
            "total_distance_m": round(result.total_distance_m, 2),
            "average_safety_score": (
                round(average_safety_score, 2)
                if average_safety_score is not None
                else None
            ),
            "total_cost": round(result.total_cost, 2),
            "cost_weights": {
                "distance": policy.distance_weight,
                "risk": policy.risk_weight,
            },
            "start_node_id": start_node.node_id,
            "end_node_id": end_node.node_id,
            "start_snap_distance_m": round(start_node.distance_m, 2),
            "end_snap_distance_m": round(end_node.distance_m, 2),
            "road_segments": [
                {
                    "id": edge.segment_id,
                    "source_id": edge.source_id,
                    "name": edge.name,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "distance_m": round(edge.distance_m, 2),
                    "streetlight_score": round(edge.streetlight_score, 2),
                    "cctv_score": round(edge.cctv_score, 2),
                    "population_score": round(edge.population_score, 2),
                    "safety_score": round(edge.safety_score, 2),
                    "distance_factor": round(
                        policy.breakdown(edge).distance_factor,
                        2,
                    ),
                    "risk_factor": round(policy.breakdown(edge).risk_factor, 2),
                    "traversal_cost": round(policy.edge_cost(edge), 2),
                }
                for edge in result.edges
            ],
        },
    }


def _get_route(
    start_longitude: float,
    start_latitude: float,
    end_longitude: float,
    end_latitude: float,
    route_type: Literal["shortest", "safe"],
    source: str | None = None,
) -> dict[str, object]:
    start_node = find_nearest_road_node(
        start_longitude,
        start_latitude,
        source=source,
    )
    end_node = find_nearest_road_node(
        end_longitude,
        end_latitude,
        source=source,
    )
    if start_node is None or end_node is None:
        raise RoutingDataNotFoundError("The road graph is empty")

    _validate_snap_distance(start_node, "start")
    _validate_snap_distance(end_node, "end")

    segments = list_routing_road_segments(source=source)
    if not segments:
        raise RoutingDataNotFoundError("The road graph is empty")

    graph = _build_graph(segments)
    settings = get_settings()
    policy = (
        SafetyCostPolicy(distance_weight=1.0, risk_weight=0.0)
        if route_type == "shortest"
        else SafetyCostPolicy(
            distance_weight=settings.safe_route_distance_weight,
            risk_weight=settings.safe_route_risk_weight,
        )
    )
    try:
        result = find_path(
            graph=graph,
            start_node_id=start_node.node_id,
            goal_node_id=end_node.node_id,
            edge_cost=policy.edge_cost,
            minimum_cost_per_meter=policy.distance_weight,
        )
    except PathNotFoundError as exc:
        raise RouteNotFoundError(str(exc)) from exc

    return _route_feature(result, start_node, end_node, route_type, policy)


def get_shortest_route(
    start_longitude: float,
    start_latitude: float,
    end_longitude: float,
    end_latitude: float,
    source: str | None = None,
) -> dict[str, object]:
    return _get_route(
        start_longitude,
        start_latitude,
        end_longitude,
        end_latitude,
        route_type="shortest",
        source=source,
    )


def get_safe_route(
    start_longitude: float,
    start_latitude: float,
    end_longitude: float,
    end_latitude: float,
    source: str | None = None,
) -> dict[str, object]:
    return _get_route(
        start_longitude,
        start_latitude,
        end_longitude,
        end_latitude,
        route_type="safe",
        source=source,
    )
