from dataclasses import replace

import pytest

from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.routing.intersection import find_intersection_aware_path
from app.services.routing.safety_cost import SafetyCostPolicy


def graph_with_bridge(ground_distance=100, bridge_distance=120, bridge_steps=False):
    graph = RoadGraph()
    graph.add_node(GraphNode(1, 0, 0))
    graph.add_node(GraphNode(2, 100, 0))
    ground = GraphEdge(
        segment_id=1, source_id="ground", name=None, from_node_id=1, to_node_id=2,
        distance_m=ground_distance, safety_score=100, streetlight_score=100,
        cctv_score=100, population_score=100, coordinates=((126.6, 37.4), (126.61, 37.4)),
        intersection_exposure_m=ground_distance * 0.4,
    )
    graph.add_edge(ground)
    graph.add_edge(replace(ground, segment_id=2, source_id="bridge", distance_m=bridge_distance,
                           grade_separated=True, pedestrian_bridge_ids=("bridge-ref",), is_steps=bridge_steps))
    return graph


def route(graph, weight, stairs=0):
    return find_intersection_aware_path(
        graph, 1, 2, SafetyCostPolicy(1, 0, stairs_weight=stairs, intersection_weight=weight), lambda _: 0,
    )


def test_weight_zero_and_low_weight_keep_short_route_but_max_can_choose_bridge():
    graph = graph_with_bridge()
    assert route(graph, 0).path.edges[0].source_id == "ground"
    assert route(graph, 0.1).path.edges[0].source_id == "ground"
    result = route(graph, 1)
    assert result.path.edges[0].source_id == "bridge"
    assert result.path.total_distance_m == 120
    assert result.distance_limit_m == 130


@pytest.mark.parametrize("distance,bridge,limit", [(100, 140, 130), (1000, 1350, 1300)])
def test_ratio_and_absolute_detour_caps(distance, bridge, limit):
    result = route(graph_with_bridge(distance, bridge), 1)
    assert result.path.total_distance_m <= limit
    assert result.path.edges[0].source_id == "ground"
    assert result.detour_limited is True
    assert result.distance_limit_m == limit


def test_stairs_are_not_waived_to_force_a_bridge():
    graph = graph_with_bridge(bridge_steps=True)
    assert route(graph, 1, stairs=0).path.edges[0].source_id == "bridge"
    assert route(graph, 1, stairs=1).path.edges[0].source_id == "ground"


def test_cost_is_nonnegative_and_grade_separated_edges_have_no_intersection_penalty():
    graph = graph_with_bridge()
    policy = SafetyCostPolicy(1, 5, stairs_weight=1, intersection_weight=1)
    ground, bridge = graph.neighbors(1)
    assert policy.breakdown(ground).intersection_penalty == 160
    assert policy.breakdown(bridge).intersection_penalty == 0
    assert policy.edge_cost(bridge) >= bridge.distance_m
    assert policy.breakdown(replace(ground, intersection_exposure_m=9999)).intersection_penalty == 400


def test_missing_references_dont_invent_crossings_or_bridges():
    graph = graph_with_bridge()
    graph.adjacency[1] = [replace(graph.neighbors(1)[0], intersection_exposure_m=0)]
    result = route(graph, 1)
    assert result.path.total_distance_m == 100
    assert not result.detour_limited


def test_same_node_returns_zero_without_division_error():
    graph = graph_with_bridge()
    result = find_intersection_aware_path(graph, 1, 1, SafetyCostPolicy(1, 0, intersection_weight=1), lambda _: 0)
    assert result.path.total_distance_m == result.distance_limit_m == 0


@pytest.mark.parametrize("weight", [-0.1, 1.1, float("nan")])
def test_invalid_weight_is_rejected(weight):
    with pytest.raises(ValueError):
        SafetyCostPolicy(1, 0, intersection_weight=weight)
