"""Soft intersection avoidance with a hard bound on additional walking distance.

The baseline keeps the same safety/stair policy. Try a small bounded family of
penalties, never claim a global resource-constrained optimum or force a bridge.
No discounts/negative costs: A*'s distance heuristic remains admissible.
"""
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.services.routing.astar import PathResult
from app.services.routing.pedestrian_priority import find_pedestrian_first_path
from app.services.routing.graph import GraphEdge, RoadGraph
from app.services.routing.safety_cost import SafetyCostPolicy

MAX_EXTRA_DISTANCE_RATIO = 0.30
MAX_EXTRA_DISTANCE_M = 300.0


@dataclass(frozen=True)
class IntersectionSearchResult:
    path: PathResult
    baseline_distance_m: float
    distance_limit_m: float
    detour_limited: bool


def find_intersection_aware_path(
    graph: RoadGraph,
    start_node_id: int,
    goal_node_id: int,
    policy: SafetyCostPolicy,
    extra_cost: Callable[[GraphEdge], float],
) -> IntersectionSearchResult:
    def cost(active: SafetyCostPolicy):
        return lambda edge: active.edge_cost(edge) + extra_cost(edge)

    def search(active: SafetyCostPolicy):
        return find_pedestrian_first_path(graph, start_node_id, goal_node_id, cost(active), active.distance_weight)

    baseline = search(replace(policy, intersection_weight=0))
    limit = baseline.total_distance_m + min(
        baseline.total_distance_m * MAX_EXTRA_DISTANCE_RATIO, MAX_EXTRA_DISTANCE_M,
    )
    desired_cost = cost(policy)
    def scored(path: PathResult) -> PathResult:
        return replace(path, total_cost=sum(desired_cost(edge) for edge in path.edges))

    candidates = [scored(baseline)]
    limited = False
    if policy.intersection_weight > 0 and any(
        edge.intersection_exposure_m > 0 and not edge.grade_separated for edge in baseline.edges
    ):
        for scale in (1.0, 0.5, 0.25, 0.125):
            trial = search(replace(policy, intersection_weight=policy.intersection_weight * scale))
            if trial.total_distance_m <= limit + 1e-6:
                candidates.append(scored(trial))
                # At full weight this is already the unconstrained optimum.
                if scale == 1.0:
                    break
            else:
                limited = True
    best = min(candidates, key=lambda path: (path.total_cost, path.total_distance_m))
    return IntersectionSearchResult(best, baseline.total_distance_m, limit, limited)
