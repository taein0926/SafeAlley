from unittest.mock import patch

import pytest

from app.schemas.agent import RouteOptimizationArguments
from app.services import route_service, route_ranking_service


@pytest.mark.parametrize("stairs,intersection", [(0, 0), (1, 1)])
def test_candidates_reuse_graph_without_changing_routes(stairs, intersection):
    arguments = RouteOptimizationArguments(
        origin={"longitude": 126.679, "latitude": 37.4608},
        destination={"longitude": 126.683, "latitude": 37.4608},
        source="test-fixture", stairs_weight=stairs, intersection_weight=intersection,
        departure_time="14:00:00",
    )
    kwargs = route_ranking_service._route_arguments(arguments)
    shortest = route_service.get_shortest_route(**kwargs)
    safe = route_service.get_safe_route(**kwargs)
    used = {s["id"] for r in (shortest, safe) for s in r["properties"]["road_segments"]}
    balanced = route_service.get_balanced_route(**kwargs, penalized_segment_ids=used)
    with (
        patch.object(route_service, "list_routing_road_segments", wraps=route_service.list_routing_road_segments) as roads,
        patch.object(route_service, "_build_graph", wraps=route_service._build_graph) as build,
        patch.object(route_service, "find_nearest_road_node", wraps=route_service.find_nearest_road_node) as snap,
    ):
        for request_number in range(1, 3):
            actual = route_ranking_service.generate_route_candidates(arguments)
            assert [c["route"] for c in actual] == [shortest, balanced, safe]
            assert roads.call_count == request_number
            assert build.call_count == request_number
            assert snap.call_count == request_number * 2
