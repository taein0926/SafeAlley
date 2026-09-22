from app.repositories.personalization_repository import (
    get_learned_preferences,
    record_selection,
    upsert_learned_preferences,
)
from app.schemas.agent import LearnedRoutePreference, RoutePreference
from app.services.route_metrics import METRIC_REGISTRY


LEARNABLE_DIRECTIONS = {
    "distance_m": "minimize",
    "safety_score": "maximize",
    "streetlight_score": "maximize",
    "cctv_score": "maximize",
    "crosswalk_count": "minimize",
    "stairs_distance_m": "minimize",
    "intersection_distance_m": "minimize",
    "sidewalk_coverage_percent": "maximize",
    "max_slope_percent": "minimize",
}
LEARNING_RATE = 0.2


def learned_preferences_for_ranking(user_id: str) -> list[RoutePreference]:
    learned = get_learned_preferences(user_id)
    return [
        RoutePreference(
            factor=factor,
            direction=LEARNABLE_DIRECTIONS[factor],
            weight=max(weight, 0.05),
        )
        for factor, (weight, observations) in learned.items()
        if factor in LEARNABLE_DIRECTIONS and observations >= 3
    ]


def _desirability(
    factor: str,
    value: float,
    values: list[float],
) -> float:
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return 0.5
    normalized = (value - minimum) / (maximum - minimum)
    if LEARNABLE_DIRECTIONS[factor] == "minimize":
        return 1.0 - normalized
    return normalized


def learn_from_selection(
    recommendation_id: str,
    user_id: str,
    selected_route_type: str,
) -> list[LearnedRoutePreference]:
    candidates, selected = record_selection(
        recommendation_id,
        user_id,
        selected_route_type,
    )
    existing = get_learned_preferences(user_id)
    updates: dict[str, float] = {}

    # New display metrics are not automatically learnable preferences.
    for factor in LEARNABLE_DIRECTIONS:
        if factor not in METRIC_REGISTRY:
            continue
        values = [
            float(candidate["metrics"][factor])
            for candidate in candidates
            if candidate["metrics"].get(factor) is not None
        ]
        selected_value = selected["metrics"].get(factor)
        if selected_value is None or len(values) != len(candidates):
            continue
        observation = _desirability(factor, float(selected_value), values)
        previous = existing.get(factor, (0.5, 0))[0]
        updates[factor] = round(
            previous * (1 - LEARNING_RATE) + observation * LEARNING_RATE,
            6,
        )

    upsert_learned_preferences(user_id, updates)
    learned = get_learned_preferences(user_id)
    return [
        LearnedRoutePreference(
            factor=factor,
            weight=round(weight, 4),
            observations=observations,
        )
        for factor, (weight, observations) in sorted(learned.items())
    ]
