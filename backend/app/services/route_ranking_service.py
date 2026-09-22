from datetime import time

from app.schemas.agent import (
    RouteOptimizationArguments,
    RoutePreference,
    UnsupportedPreference,
)
from app.services.route_metrics import METRIC_REGISTRY, calculate_route_metrics
from app.services.route_service import (
    get_balanced_route,
    get_safe_route,
    get_shortest_route,
)
from app.repositories.personalization_repository import save_recommendation
from app.services.personalization_service import learned_preferences_for_ranking


NIGHT_START = time(20, 0)
NIGHT_END = time(6, 0)
NIGHT_WEIGHT_MULTIPLIERS = {
    "safety_score": 1.5,
    "streetlight_score": 2.0,
    "cctv_score": 1.5,
}


def _route_arguments(arguments: RouteOptimizationArguments) -> dict[str, object]:
    return {
        "start_longitude": arguments.origin.longitude,
        "start_latitude": arguments.origin.latitude,
        "end_longitude": arguments.destination.longitude,
        "end_latitude": arguments.destination.latitude,
        "source": arguments.source,
        "stairs_weight": arguments.stairs_weight,
    }


def _is_night(departure_time: time | None) -> bool:
    return departure_time is not None and (
        departure_time >= NIGHT_START or departure_time < NIGHT_END
    )


def _default_preferences(departure_time: time | None) -> list[RoutePreference]:
    if not _is_night(departure_time):
        return [RoutePreference(factor="distance_m", direction="minimize", weight=1.0)]
    return [
        RoutePreference(factor="distance_m", direction="minimize", weight=1.0),
        RoutePreference(factor="safety_score", direction="maximize", weight=1.5),
        RoutePreference(factor="streetlight_score", direction="maximize", weight=2.0),
        RoutePreference(factor="cctv_score", direction="maximize", weight=1.5),
    ]


def _apply_time_policy(
    preferences: list[RoutePreference],
    departure_time: time | None,
) -> list[RoutePreference]:
    if not _is_night(departure_time):
        return preferences
    return [
        preference.model_copy(
            update={
                "weight": preference.weight
                * NIGHT_WEIGHT_MULTIPLIERS.get(preference.factor, 1.0)
            }
        )
        for preference in preferences
    ]


def _supported_preferences(
    preferences: list[RoutePreference],
    candidates: list[dict[str, object]],
) -> tuple[list[RoutePreference], list[UnsupportedPreference]]:
    supported: list[RoutePreference] = []
    unsupported: list[UnsupportedPreference] = []
    for preference in preferences:
        if preference.factor not in METRIC_REGISTRY:
            unsupported.append(
                UnsupportedPreference(
                    factor=preference.factor,
                    reason="No metric or validated source data is registered for this factor",
                )
            )
            continue
        values = [
            candidate["metrics"].get(preference.factor)
            for candidate in candidates
        ]
        if not values or any(value is None for value in values):
            unsupported.append(
                UnsupportedPreference(
                    factor=preference.factor,
                    reason="The metric is registered but data is unavailable for one or more candidate routes",
                )
            )
            continue
        supported.append(preference)
    return supported, unsupported


def _normalized_value(
    value: float,
    values: list[float],
    direction: str,
) -> float:
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return 1.0
    if direction == "maximize":
        return (value - minimum) / (maximum - minimum)
    return (maximum - value) / (maximum - minimum)


def _score_candidates(
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
) -> None:
    total_weight = sum(preference.weight for preference in preferences)
    for candidate in candidates:
        score = 0.0
        for preference in preferences:
            available = [
                float(other["metrics"][preference.factor])
                for other in candidates
                if other["metrics"].get(preference.factor) is not None
            ]
            value = candidate["metrics"].get(preference.factor)
            if value is None or not available:
                continue
            score += (
                _normalized_value(float(value), available, preference.direction)
                * preference.weight
            )
        candidate["preference_score"] = round(score / total_weight * 100, 2)


def _semantic_tie_break_score(
    candidate: dict[str, object],
    preferences: list[RoutePreference],
) -> float:
    """Prefer the named route profile when normalized metrics are identical."""

    route_type = candidate["route_type"]
    distance_weight = sum(
        preference.weight
        for preference in preferences
        if preference.factor == "distance_m"
    )
    safety_weight = sum(
        preference.weight
        for preference in preferences
        if preference.factor != "distance_m"
    )
    if route_type == "shortest":
        return distance_weight
    if route_type == "safe":
        return safety_weight
    return (distance_weight + safety_weight) / 2


def generate_route_candidates(
    arguments: RouteOptimizationArguments,
) -> list[dict[str, object]]:
    """Generate route alternatives independently from preference scoring."""

    route_arguments = _route_arguments(arguments)
    shortest_route = get_shortest_route(**route_arguments)
    safe_route = get_safe_route(**route_arguments)
    used_segment_ids = {
        int(segment["id"])
        for route in (shortest_route, safe_route)
        for segment in route["properties"].get("road_segments", [])
    }
    balanced_route = get_balanced_route(
        **route_arguments,
        penalized_segment_ids=used_segment_ids,
    )
    routes = [shortest_route, balanced_route, safe_route]
    return [
        {
            "route_type": route["properties"]["route_type"],
            "preference_score": None,
            "metrics": calculate_route_metrics(route),
            "route": route,
        }
        for route in routes
    ]


def rank_generated_candidates(
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
) -> tuple[dict[str, object] | None, list[UnsupportedPreference]]:
    """Score already-generated alternatives using only complete metric data."""

    supported, unsupported = _supported_preferences(preferences, candidates)

    selected: dict[str, object] | None = None
    if supported:
        avoidance = [item for item in supported if item.direction == "avoid"]
        hard_constraint_eligible = [
            candidate for candidate in candidates
            if all(float(candidate["metrics"][item.factor]) <= 0 for item in avoidance)
        ]
        if not hard_constraint_eligible:
            unsupported.extend(
                UnsupportedPreference(
                    factor=item.factor,
                    reason="No generated route satisfies this hard avoidance condition",
                ) for item in avoidance
            )
            return None, unsupported
        eligible = [
            candidate for candidate in hard_constraint_eligible
            if candidate["route"]["properties"].get("unverified_major_road_count", 0) == 0
        ]
        if not eligible:
            return None, unsupported
        _score_candidates(eligible, supported)
        selected = max(
            eligible,
            key=lambda candidate: (
                float(candidate["preference_score"]),
                _semantic_tie_break_score(candidate, supported),
            ),
        )
    return selected, unsupported


def rank_route_candidates(arguments: RouteOptimizationArguments) -> dict[str, object]:
    #1. 최단 경로와 안전 경로 후보 생성
    candidates = generate_route_candidates(arguments)
    #2. 사용자 조건이없으면 시간대별 기본 조건 사용
    if arguments.preferences:
        requested_preferences = arguments.preferences
    elif arguments.user_id:
        requested_preferences = learned_preferences_for_ranking(arguments.user_id)
        if not requested_preferences:
            requested_preferences = _default_preferences(arguments.departure_time)
    else:
        requested_preferences = _default_preferences(arguments.departure_time)
    #3. 야간이면 안전 관련 가중치 적용
    effective_preferences = _apply_time_policy(
        requested_preferences,
        arguments.departure_time,
    )
    #4. 후보 경로 점수 계산 및 최종 경로 선택
    selected, unsupported = rank_generated_candidates(
        candidates,
        effective_preferences,
    )
    field_review_required = selected is None and any(
        candidate["route"]["properties"].get("unverified_major_road_count", 0) > 0
        for candidate in candidates
    ) and all(
        candidate["route"]["properties"].get("unverified_major_road_count", 0) > 0
        for candidate in candidates
    )
    recommendation_status = (
        "field_review_required" if field_review_required
        else "ready" if selected else "no_supported_preferences"
    )

    recommendation_id = (
        save_recommendation(arguments.user_id, candidates)
        if arguments.user_id and not field_review_required
        else None
    )

    #5. API에 결과 반환
    return {
        "recommendation_id": recommendation_id,
        "selected_route_type": selected["route_type"] if selected else None,
        "selected_route": selected["route"] if selected else None,
        "recommendation_status": recommendation_status,
        "candidates": candidates,
        "unsupported_preferences": unsupported,
    }
