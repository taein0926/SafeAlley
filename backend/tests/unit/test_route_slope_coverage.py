from dataclasses import replace

from app.repositories.road_repository import NearestRoadNode
from app.schemas.route import RouteFeature
from app.services.route_service import _route_feature
from app.services.routing.astar import PathResult
from app.services.routing.graph import GraphEdge
from app.services.routing.safety_cost import SafetyCostPolicy


def _edge(segment_id: int, slope: float | None) -> GraphEdge:
    return GraphEdge(
        segment_id=segment_id, source_id=f"test-{segment_id}", name=None,
        from_node_id=segment_id, to_node_id=segment_id + 1,
        distance_m=20, streetlight_score=50, cctv_score=50,
        population_score=50, safety_score=50,
        coordinates=((126.68, 37.46), (126.681, 37.46)),
        incline_percent=slope,
    )


def test_partial_slope_coverage_is_not_reported_as_route_maximum() -> None:
    node = NearestRoadNode(1, 0, 0, 126.68, 37.46, 0)
    policy = SafetyCostPolicy(distance_weight=1, risk_weight=0)
    partial = _route_feature(
        PathResult((_edge(1, 8), _edge(2, None)), 40, 40),
        node, node, "shortest", policy,
    )["properties"]
    assert partial["slope_coverage_percent"] == 50
    assert partial["max_slope_percent"] is None

    complete = _route_feature(
        PathResult((_edge(1, 8), _edge(2, 4)), 40, 40),
        node, node, "shortest", policy,
    )["properties"]
    assert complete["slope_coverage_percent"] == 100
    assert complete["max_slope_percent"] == 8


def test_review_flags_are_internal_only_and_not_serialized_in_route_response() -> None:
    node = NearestRoadNode(1, 0, 0, 126.68, 37.46, 0)
    policy = SafetyCostPolicy(distance_weight=1, risk_weight=0)
    fallback = replace(_edge(1, None), walkability_class="major_road_fallback")
    feature = _route_feature(
        PathResult((fallback,), 20, 20), node, node, "shortest", policy,
    )
    properties = feature["properties"]

    assert properties["unverified_major_road_count"] == 1
    payload = RouteFeature.model_validate(feature).model_dump(mode="json")
    for key in ("review_status", "unverified_major_road_count", "unverified_major_road_source_ids"):
        assert key not in payload["properties"]
    assert "field_status" not in payload["properties"]["road_segments"][0]
    assert payload["properties"]["total_cost"] == properties["total_cost"]
    assert payload["geometry"] == feature["geometry"]

    reviewed = replace(fallback, field_status="verified_walkable")
    reviewed_properties = _route_feature(
        PathResult((reviewed,), 20, 20), node, node, "shortest", policy,
    )["properties"]
    assert reviewed_properties["unverified_major_road_count"] == 0
