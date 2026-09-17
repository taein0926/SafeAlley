import pytest

from app.services.routing.astar import find_path
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.routing.safety_cost import SafetyCostPolicy


def add_edge(
    graph: RoadGraph,
    segment_id: int,
    from_node_id: int,
    to_node_id: int,
    distance_m: float,
    safety_score: float,
) -> None:
    graph.add_edge(
        GraphEdge(
            segment_id=segment_id,
            source_id=f"test-{segment_id}",
            name=None,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            distance_m=distance_m,
            streetlight_score=safety_score,
            cctv_score=safety_score,
            population_score=safety_score,
            safety_score=safety_score,
            coordinates=((0.0, 0.0), (1.0, 1.0)),
        )
    )


def test_safe_cost_can_choose_a_longer_but_safer_path() -> None:
    graph = RoadGraph()
    for node in (
        GraphNode(id=1, x=0, y=0),
        GraphNode(id=2, x=10, y=0),
        GraphNode(id=3, x=0, y=10),
        GraphNode(id=4, x=20, y=0),
    ):
        graph.add_node(node)

    add_edge(graph, 101, 1, 2, distance_m=10, safety_score=10)
    add_edge(graph, 102, 2, 4, distance_m=10, safety_score=10)
    add_edge(graph, 201, 1, 3, distance_m=15, safety_score=100)
    add_edge(graph, 202, 3, 4, distance_m=15, safety_score=100)

    policy = SafetyCostPolicy(distance_weight=1, risk_weight=5)
    result = find_path(
        graph=graph,
        start_node_id=1,
        goal_node_id=4,
        edge_cost=policy.edge_cost,
        minimum_cost_per_meter=policy.distance_weight,
    )

    assert [edge.segment_id for edge in result.edges] == [201, 202]
    assert result.total_distance_m == pytest.approx(30)
    assert result.total_cost == pytest.approx(30)
