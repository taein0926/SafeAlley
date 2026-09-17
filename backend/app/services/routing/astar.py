from collections.abc import Callable
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from math import hypot

from app.services.routing.graph import GraphEdge, RoadGraph


class PathNotFoundError(RuntimeError):
    """Raised when two graph nodes have no traversable path."""


@dataclass(frozen=True)
class PathResult:
    edges: tuple[GraphEdge, ...]
    total_distance_m: float
    total_cost: float


def _heuristic(
    graph: RoadGraph,
    node_id: int,
    goal_node_id: int,
    minimum_cost_per_meter: float,
) -> float:
    node = graph.nodes[node_id]
    goal = graph.nodes[goal_node_id]
    return hypot(goal.x - node.x, goal.y - node.y) * minimum_cost_per_meter


def find_path(
    graph: RoadGraph,
    start_node_id: int,
    goal_node_id: int,
    edge_cost: Callable[[GraphEdge], float],
    minimum_cost_per_meter: float,
) -> PathResult:
    if minimum_cost_per_meter < 0:
        raise ValueError("A* minimum cost per meter cannot be negative")
    if start_node_id not in graph.nodes or goal_node_id not in graph.nodes:
        raise PathNotFoundError("Start or goal node does not exist in the road graph")

    if start_node_id == goal_node_id:
        return PathResult(edges=(), total_distance_m=0.0, total_cost=0.0)

    sequence = count()
    frontier: list[tuple[float, float, int, int]] = []
    heappush(
        frontier,
        (
            _heuristic(
                graph,
                start_node_id,
                goal_node_id,
                minimum_cost_per_meter,
            ),
            0.0,
            next(sequence),
            start_node_id,
        ),
    )

    best_cost: dict[int, float] = {start_node_id: 0.0}
    came_from: dict[int, GraphEdge] = {}

    while frontier:
        _, current_cost, _, current_node_id = heappop(frontier)
        if current_cost > best_cost.get(current_node_id, float("inf")):
            continue
        if current_node_id == goal_node_id:
            break

        for edge in graph.neighbors(current_node_id):
            traversal_cost = edge_cost(edge)
            if traversal_cost < 0:
                raise ValueError("A* edge cost cannot be negative")
            next_cost = current_cost + traversal_cost
            if next_cost >= best_cost.get(edge.to_node_id, float("inf")):
                continue

            best_cost[edge.to_node_id] = next_cost
            came_from[edge.to_node_id] = edge
            priority = next_cost + _heuristic(
                graph,
                edge.to_node_id,
                goal_node_id,
                minimum_cost_per_meter,
            )
            heappush(
                frontier,
                (priority, next_cost, next(sequence), edge.to_node_id),
            )

    if goal_node_id not in came_from:
        raise PathNotFoundError("No traversable path connects the requested nodes")

    edges: list[GraphEdge] = []
    current_node_id = goal_node_id
    while current_node_id != start_node_id:
        edge = came_from[current_node_id]
        edges.append(edge)
        current_node_id = edge.from_node_id
    edges.reverse()

    return PathResult(
        edges=tuple(edges),
        total_distance_m=sum(edge.distance_m for edge in edges),
        total_cost=best_cost[goal_node_id],
    )


def find_shortest_path(
    graph: RoadGraph,
    start_node_id: int,
    goal_node_id: int,
) -> PathResult:
    return find_path(
        graph=graph,
        start_node_id=start_node_id,
        goal_node_id=goal_node_id,
        edge_cost=lambda edge: edge.distance_m,
        minimum_cost_per_meter=1.0,
    )
