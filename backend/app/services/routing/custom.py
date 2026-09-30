"""Request-aware paths; no artificial diversity penalty or hidden third route."""
from dataclasses import replace
from math import inf

from app.services.routing.astar import find_path
from app.services.routing.safety_cost import SafetyCostPolicy


def custom_policy(preferences, *, stairs_weight, crossing_weight, is_night, settings):
    facilities = tuple((p.factor, p.weight) for p in preferences
                       if p.factor in {"safety_score", "streetlight_score", "cctv_score"}
                       and p.direction == "maximize" and (is_night or p.factor != "streetlight_score"))
    facility_weight = sum(w for _, w in facilities)
    distance_weight = sum(p.weight for p in preferences if p.factor == "distance_m")
    largest = max((p.weight for p in preferences), default=1)
    for p in preferences:
        if p.direction in {"minimize", "avoid"}:
            if p.factor == "stairs_distance_m":
                stairs_weight = stairs_weight or min(1, p.weight / largest)
            if p.factor == "crosswalk_count":
                crossing_weight = crossing_weight or min(1, p.weight / largest)
    return SafetyCostPolicy(
        distance_weight=1,
        risk_weight=settings.safe_route_risk_weight * facility_weight / max(facility_weight + distance_weight, 1e-9),
        stairs_weight=stairs_weight, crossing_weight=crossing_weight,
        streetlight_included=is_night, cctv_weight=settings.safety_cctv_weight,
        help_point_weight=settings.safety_help_point_weight,
        preference_components=facilities, pedestrian_weight=0.5,
    )


def find_custom_path(graph, start, goal, policy, preferences):
    avoid = {p.factor for p in preferences if p.direction == "avoid"}

    def extra(edge):
        if "stairs_distance_m" in avoid and edge.is_steps:
            return inf
        if "crosswalk_count" in avoid and (edge.crossing_group is not None or edge.centreline_fallback or not edge.pedestrian_version):
            return inf
        sidewalk = next((p for p in preferences if p.factor == "sidewalk_coverage_percent"), None)
        if sidewalk and sidewalk.direction == "maximize" and not edge.sidewalk_confirmed:
            return edge.distance_m * min(1, sidewalk.weight / max(p.weight for p in preferences))
        return 0.0

    def search(active):
        return find_path(graph, start, goal, lambda e: active.edge_cost(e) + extra(e), 1.0)

    baseline = search(replace(policy, crossing_weight=0))
    limit = baseline.total_distance_m + min(baseline.total_distance_m * .30, 300)
    cost = lambda e: policy.edge_cost(e) + extra(e)
    score = lambda p: replace(p, total_cost=sum(cost(e) for e in p.edges))
    candidates = [score(baseline)]
    limited = False
    if policy.crossing_weight:
        for scale in (1, .5, .25, .125):
            trial = search(replace(policy, crossing_weight=policy.crossing_weight * scale))
            if trial.total_distance_m <= limit + 1e-6:
                candidates.append(score(trial))
                if scale == 1:
                    break
            else:
                limited = True
    return min(candidates, key=lambda p: (p.total_cost, p.total_distance_m)), baseline.total_distance_m, limit, limited
