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
    *,
    is_steps: bool = False,
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
            highway="steps" if is_steps else "footway",
            is_steps=is_steps,
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


def test_stairs_weight_zero_preserves_existing_edge_cost() -> None:
    edge_graph = RoadGraph()
    edge_graph.add_node(GraphNode(id=1, x=0, y=0))
    edge_graph.add_node(GraphNode(id=2, x=10, y=0))
    add_edge(edge_graph, 101, 1, 2, 10, 50, is_steps=True)
    edge = edge_graph.neighbors(1)[0]

    baseline = SafetyCostPolicy(distance_weight=1, risk_weight=2)
    with_zero_weight = SafetyCostPolicy(
        distance_weight=1,
        risk_weight=2,
        stairs_weight=0,
    )

    assert with_zero_weight.edge_cost(edge) == pytest.approx(
        baseline.edge_cost(edge)
    )
    assert with_zero_weight.breakdown(edge).stairs_penalty == 0


def test_stairs_weight_can_choose_non_stairs_alternative() -> None:
    graph = RoadGraph()
    for node in (
        GraphNode(id=1, x=0, y=0),
        GraphNode(id=2, x=10, y=0),
        GraphNode(id=3, x=5, y=5),
    ):
        graph.add_node(node)
    add_edge(graph, 101, 1, 2, 10, 100, is_steps=True)
    add_edge(graph, 201, 1, 3, 6, 100)
    add_edge(graph, 202, 3, 2, 6, 100)

    no_avoidance = SafetyCostPolicy(1, 0, stairs_weight=0)
    strong_avoidance = SafetyCostPolicy(1, 0, stairs_weight=1)
    direct = find_path(graph, 1, 2, no_avoidance.edge_cost, 1)
    avoided = find_path(graph, 1, 2, strong_avoidance.edge_cost, 1)

    assert [edge.segment_id for edge in direct.edges] == [101]
    assert direct.total_cost == pytest.approx(10)
    assert [edge.segment_id for edge in avoided.edges] == [201, 202]
    assert avoided.total_cost == pytest.approx(12)


def test_stairs_remain_traversable_when_they_are_the_only_path() -> None:
    graph = RoadGraph()
    graph.add_node(GraphNode(id=1, x=0, y=0))
    graph.add_node(GraphNode(id=2, x=10, y=0))
    add_edge(graph, 101, 1, 2, 10, 100, is_steps=True)
    policy = SafetyCostPolicy(1, 0, stairs_weight=1)

    result = find_path(graph, 1, 2, policy.edge_cost, 1)

    assert [edge.segment_id for edge in result.edges] == [101]
    assert result.total_cost == pytest.approx(30)


@pytest.mark.parametrize("stairs_weight", [-0.01, 1.01])
def test_stairs_weight_must_be_between_zero_and_one(stairs_weight: float) -> None:
    with pytest.raises(ValueError):
        SafetyCostPolicy(1, 0, stairs_weight=stairs_weight)
