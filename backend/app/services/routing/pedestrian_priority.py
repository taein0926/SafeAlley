"""Prefer mapped walking space before optimizing crossing/facility costs."""
from heapq import heappop, heappush
from itertools import count
from math import isfinite
from collections.abc import Callable, Iterable

from app.services.routing.astar import PathNotFoundError, PathResult, find_path
from app.services.routing.graph import GraphEdge, RoadGraph


def is_preferred_walking_edge(edge: GraphEdge) -> bool:
    # Crossings are part of the walking network, not a reason to leave it.
    return (edge.highway in {"footway", "path", "pedestrian", "steps", "living_street"}
            or edge.is_steps
            or (edge.sidewalk_confirmed and not edge.centreline_fallback))


def nonpreferred_distance(edges: Iterable[GraphEdge]) -> float:
    return sum(e.distance_m for e in edges if not is_preferred_walking_edge(e))


def find_pedestrian_first_path(
    graph: RoadGraph, start_node_id: int, goal_node_id: int,
    edge_cost: Callable[[GraphEdge], float], minimum_cost_per_meter: float = 1.0,
) -> PathResult:
    if minimum_cost_per_meter < 0:
        raise ValueError("Minimum cost per meter cannot be negative")
    # Legacy/synthetic graphs without walking classifications keep their existing policy.
    if not any(e.highway is not None and is_preferred_walking_edge(e)
               for edges in graph.adjacency.values() for e in edges):
        return find_path(graph, start_node_id, goal_node_id, edge_cost, minimum_cost_per_meter)
    if start_node_id not in graph.nodes or goal_node_id not in graph.nodes:
        raise PathNotFoundError("Start or goal node does not exist in the road graph")
    if start_node_id == goal_node_id:
        return PathResult((), 0.0, 0.0)
    # Lexicographic Dijkstra: no finite crossing penalty can buy a carriageway shortcut.
    sequence = count()
    queue = [(0.0, 0.0, next(sequence), start_node_id)]
    best = {start_node_id: (0.0, 0.0)}
    previous = {}
    while queue:
        outside, cost, _, node = heappop(queue)
        if (outside, cost) != best.get(node):
            continue
        if node == goal_node_id:
            break
        for edge in graph.neighbors(node):
            weight = edge_cost(edge)
            if weight < 0:
                raise ValueError("Edge cost cannot be negative")
            if not isfinite(weight):
                continue  # Never relax an explicit avoidance constraint.
            value = (outside + (0 if is_preferred_walking_edge(edge) else edge.distance_m), cost + weight)
            if value >= best.get(edge.to_node_id, (float('inf'), float('inf'))):
                continue
            best[edge.to_node_id] = value
            previous[edge.to_node_id] = edge
            heappush(queue, (*value, next(sequence), edge.to_node_id))
    if goal_node_id not in previous:
        raise PathNotFoundError("No traversable path connects the requested nodes")
    edges = []
    node = goal_node_id
    while node != start_node_id:
        edge = previous[node]
        edges.append(edge)
        node = edge.from_node_id
    edges.reverse()
    return PathResult(tuple(edges), sum(e.distance_m for e in edges), best[goal_node_id][1])
