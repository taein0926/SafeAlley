from datetime import time

from app.schemas.agent import (
    RouteOptimizationArguments,
    RoutePreference,
    UnsupportedPreference,
)
from app.services.route_metrics import METRIC_REGISTRY, calculate_route_metrics
from app.services.route_service import get_safe_route, get_shortest_route


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


def generate_route_candidates(
    arguments: RouteOptimizationArguments,
) -> list[dict[str, object]]:
    """Generate route alternatives independently from preference scoring."""

    route_arguments = _route_arguments(arguments)
    routes = [
        get_shortest_route(**route_arguments),
        get_safe_route(**route_arguments),
    ]
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
        _score_candidates(candidates, supported)
        selected = max(
            candidates,
            key=lambda candidate: float(candidate["preference_score"]),
        )
    return selected, unsupported


def rank_route_candidates(arguments: RouteOptimizationArguments) -> dict[str, object]:
    candidates = generate_route_candidates(arguments)
    requested_preferences = arguments.preferences or _default_preferences(
        arguments.departure_time
    )
    effective_preferences = _apply_time_policy(
        requested_preferences,
        arguments.departure_time,
    )
    selected, unsupported = rank_generated_candidates(
        candidates,
        effective_preferences,
    )

    return {
        "selected_route_type": selected["route_type"] if selected else None,
        "selected_route": selected["route"] if selected else None,
        "candidates": candidates,
        "unsupported_preferences": unsupported,
    }
