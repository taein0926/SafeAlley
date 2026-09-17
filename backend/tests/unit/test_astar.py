import pytest

from app.services.routing.astar import PathNotFoundError, find_shortest_path
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph


def add_edge(
    graph: RoadGraph,
    segment_id: int,
    from_node_id: int,
    to_node_id: int,
    distance_m: float,
) -> None:
    graph.add_edge(
        GraphEdge(
            segment_id=segment_id,
            source_id=f"test-{segment_id}",
            name=None,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            distance_m=distance_m,
            streetlight_score=50,
            cctv_score=50,
            population_score=50,
            safety_score=50,
            coordinates=((0.0, 0.0), (1.0, 1.0)),
        )
    )


def test_astar_returns_actual_shortest_path_for_sample_graph() -> None:
    graph = RoadGraph()
    for node in (
        GraphNode(id=1, x=0, y=0),
        GraphNode(id=2, x=10, y=0),
        GraphNode(id=3, x=0, y=5),
        GraphNode(id=4, x=20, y=0),
    ):
        graph.add_node(node)

    add_edge(graph, 101, 1, 2, 10)
    add_edge(graph, 102, 2, 4, 10)
    add_edge(graph, 103, 1, 3, 5)
    add_edge(graph, 104, 3, 4, 30)
    add_edge(graph, 105, 1, 4, 50)

    result = find_shortest_path(graph, 1, 4)

    assert [edge.segment_id for edge in result.edges] == [101, 102]
    assert result.total_distance_m == pytest.approx(20)


def test_astar_returns_empty_path_when_start_equals_goal() -> None:
    graph = RoadGraph()
    graph.add_node(GraphNode(id=1, x=0, y=0))

    result = find_shortest_path(graph, 1, 1)

    assert result.edges == ()
    assert result.total_distance_m == 0


def test_astar_raises_when_no_path_exists() -> None:
    graph = RoadGraph()
    graph.add_node(GraphNode(id=1, x=0, y=0))
    graph.add_node(GraphNode(id=2, x=1, y=0))

    with pytest.raises(PathNotFoundError):
        find_shortest_path(graph, 1, 2)
