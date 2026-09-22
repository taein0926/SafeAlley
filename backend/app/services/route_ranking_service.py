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
    prepare_route,
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

PRIORITY_PHRASES = {
    "distance_m": "거리를 우선해",
    "safety_score": "가로등·CCTV·도움시설이 길 주변 어디에 있는지 살펴",
    "streetlight_score": "가로등이 길 주변 어디에 있는지 살펴",
    "cctv_score": "CCTV가 길 주변 어디에 있는지 살펴",
    "crosswalk_count": "지도에 표시된 횡단보도 수를 비교해",
    "intersection_distance_m": "교차로 주변 구간을 피하는 조건으로",
    "stairs_distance_m": "지도에 표시된 계단 구간을 피하는 조건으로",
    "sidewalk_coverage_percent": "지도에 표시된 보행공간을 참고해",
    "max_slope_percent": "지도에 기록된 경사를 참고해",
}
METRIC_NAMES = {
    "distance_m": "거리",
    "safety_score": "안전 관련 시설 지표",
    "streetlight_score": "가로등 위치 지표",
    "cctv_score": "CCTV 위치 지표",
    "crosswalk_count": "OSM 횡단보도 수",
    "intersection_distance_m": "교차로 주변 구간 회피",
    "stairs_distance_m": "계단 구간 회피",
    "stairs": "계단",
    "sidewalk_coverage_percent": "보행공간 비율",
    "max_slope_percent": "경사",
    "population_score": "유동인구",
    "police_accessibility": "경찰 도움시설 접근성",
}
PROXY_FACTORS = {"safety_score", "streetlight_score", "cctv_score"}
PROXY_SUBJECTS = {
    "safety_score": "가로등·CCTV·도움시설의 위치",
    "streetlight_score": "길 주변 가로등 위치",
    "cctv_score": "길 주변 CCTV 위치",
}
PROXY_COMPARISONS = {
    "safety_score": "가로등·CCTV·도움시설의 위치가 비교한 다른 길보다 조건에 더 잘 맞아",
    "streetlight_score": "가로등이 비교한 다른 길보다 경로 주변에 더 잘 분포해 있어",
    "cctv_score": "CCTV가 비교한 다른 길보다 경로 주변에 더 잘 분포해 있어",
}


def _route_arguments(arguments: RouteOptimizationArguments) -> dict[str, object]:
    return {
        "start_longitude": arguments.origin.longitude,
        "start_latitude": arguments.origin.latitude,
        "end_longitude": arguments.destination.longitude,
        "end_latitude": arguments.destination.latitude,
        "source": arguments.source,
        "stairs_weight": arguments.stairs_weight,
        "intersection_weight": arguments.intersection_weight,
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


def _distance_text(distance_m: float) -> str:
    return f"{distance_m / 1000:.2f}km" if distance_m >= 1000 else f"{distance_m:.0f}m"


def _route_identity(candidate: dict[str, object]) -> tuple[object, ...]:
    route = candidate["route"]
    segments = route["properties"].get("road_segments") or []
    if segments:
        return tuple(segment["source_id"] for segment in segments)
    return tuple(tuple(point) for point in route["geometry"]["coordinates"])


def _recommendation_explanation(
    selected: dict[str, object] | None,
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
    unsupported: list[UnsupportedPreference],
    status: str,
    departure_time: time | None,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    excluded = [
        candidate for candidate in candidates
        if candidate["route"]["properties"].get("unverified_major_road_count", 0) > 0
    ]
    if status == "field_review_required":
        summary = "현재 도로 자료만으로는 이 경로의 보행 가능 여부를 판단할 수 없어 자동 추천을 보류했습니다."
        notes.append("비교한 길 모두 큰 도로의 보행로 정보가 부족합니다. 위험하다는 뜻은 아닙니다.")
    elif selected is None:
        summary = (
            "요청한 회피 조건을 만족하는 경로가 없어 자동 추천을 보류했습니다."
            if any("hard avoidance" in item.reason for item in unsupported)
            else "요청 조건을 평가할 자료가 부족해 경로를 자동 추천하지 않았습니다."
        )
    else:
        unsupported_factors = {item.factor for item in unsupported}
        supported = [item for item in preferences if item.factor not in unsupported_factors]
        primary = max(supported, key=lambda item: item.weight)
        distance = float(selected["metrics"]["distance_m"])
        priority = PRIORITY_PHRASES.get(primary.factor, "요청 조건을 우선해")
        if primary.factor in PROXY_SUBJECTS:
            summary = f"{PROXY_SUBJECTS[primary.factor]}를 고려해 이 길을 추천했어요."
        else:
            summary = f"{priority} 약 {_distance_text(distance)} 길을 골랐어요."
        eligible = [
            candidate for candidate in candidates
            if candidate is not selected
            and candidate["route"]["properties"].get("unverified_major_road_count", 0) == 0
            and _route_identity(candidate) != _route_identity(selected)
            and all(
                candidate["metrics"].get(item.factor) is not None
                and float(candidate["metrics"][item.factor]) <= 0
                for item in supported if item.direction == "avoid"
            )
        ]
        if eligible:
            comparison = min(eligible, key=lambda item: float(item["metrics"]["distance_m"]))
            difference = float(comparison["metrics"]["distance_m"]) - distance
            compared = [selected, *eligible]
            primary_values = {
                float(candidate["metrics"][primary.factor]) for candidate in compared
            }
            if primary.factor != "distance_m" and len(primary_values) == 1:
                value = next(iter(primary_values))
                shortest_distance = min(
                    float(candidate["metrics"]["distance_m"])
                    for candidate in compared
                )
                if primary.factor == "stairs_distance_m" and value == 0:
                    premise = "비교한 경로 모두 지도 자료상 계단 구간이 없어서"
                elif primary.factor == "crosswalk_count" and value == 0:
                    premise = "비교한 경로 모두 지도 자료상 횡단보도 수가 0개여서"
                elif primary.factor == "sidewalk_coverage_percent" and value == 0:
                    premise = "비교한 경로 모두 확인된 보행공간 비율이 0%여서"
                else:
                    label = METRIC_NAMES.get(primary.factor, "요청 조건")
                    premise = f"비교한 경로의 {label}에 차이가 없어서"
                if distance <= shortest_distance + 0.5:
                    summary = f"{premise}, 그중 가장 짧은 길을 추천했어요."
                else:
                    summary = f"{premise}, 다른 요청 조건을 반영해 이 길을 추천했어요."
            elif primary.factor == "distance_m":
                if difference > max(10, distance * 0.01):
                    summary += f" 비교한 다른 길보다 약 {difference:.0f}m 짧아요."
                elif abs(difference) > 0.5:
                    summary += f" 다른 길과의 거리 차이는 약 {abs(difference):.0f}m로 거의 같아요."
            else:
                chosen_value = selected["metrics"].get(primary.factor)
                other_value = comparison["metrics"].get(primary.factor)
                if chosen_value is not None and other_value is not None:
                    change = float(chosen_value) - float(other_value)
                    better = change > 1 if primary.direction == "maximize" else change < -1
                    if better:
                        if primary.factor in PROXY_SUBJECTS:
                            summary = (
                                f"{PROXY_COMPARISONS[primary.factor]} "
                                "이 길을 추천했어요."
                            )
                            if difference < -10:
                                summary += f" 대신 약 {-difference:.0f}m 더 걸어요."
                        else:
                            metric_name = METRIC_NAMES.get(primary.factor, "요청 조건")
                            direction = "높아요" if primary.direction == "maximize" else "낮아요"
                            advantage = f"다른 길보다 {metric_name} 값이 더 {direction}"
                            if difference < -10:
                                summary += f" 약 {-difference:.0f}m 더 걷지만, {advantage}"
                            else:
                                summary += f" {advantage}"
        if (
            eligible
            and primary.factor != "stairs_distance_m"
            and any(
                item.factor == "stairs_distance_m" and item.direction == "avoid"
                for item in supported
            )
            and all(
                float(candidate["metrics"]["stairs_distance_m"]) == 0
                for candidate in [selected, *eligible]
            )
        ):
            summary += " 비교한 경로는 모두 지도 자료상 계단 구간이 없어요."
        if excluded:
            notes.append(
                f"다른 길 {len(excluded)}개는 큰 도로의 보행로 정보가 없어 추천에서 뺐어요."
            )
        if _is_night(departure_time) and any(item.factor in PROXY_FACTORS for item in supported):
            notes.append("밤 시간 질문으로 처리했지만, 가로등 점등 상태나 CCTV 작동 여부는 알 수 없습니다.")
        if any(item.factor in PROXY_FACTORS for item in supported):
            notes.append("지도에 등록된 시설 위치만 비교했습니다. 실제 치안이나 안전을 보장하지 않습니다.")
    for item in unsupported:
        label = METRIC_NAMES.get(item.factor, item.factor.replace("_", " "))
        if item.factor == "max_slope_percent":
            notes.append("경사는 전 구간 측정 자료가 없어 추천 조건에 반영하지 않았습니다. DEM은 현재 적재되지 않았습니다.")
        elif "hard avoidance" in item.reason:
            notes.append(f"{label} 요청을 충족하는 후보가 없어 해당 조건을 반영하지 않았습니다.")
        else:
            notes.append(f"{label} 요청은 검증된 측정값이 없어 반영하지 않았습니다.")
    notes.append("지도 자료만으로 실제 길 상태나 통행 가능 여부를 보장할 수 없습니다.")
    return summary, notes


def generate_route_candidates(
    arguments: RouteOptimizationArguments,
) -> list[dict[str, object]]:
    """Generate route alternatives independently from preference scoring."""

    route_arguments = _route_arguments(arguments)
    route_arguments["prepared"] = prepare_route(
        start_longitude=arguments.origin.longitude,
        start_latitude=arguments.origin.latitude,
        end_longitude=arguments.destination.longitude,
        end_latitude=arguments.destination.latitude,
        source=arguments.source,
    )
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
        if all(
            len({float(candidate["metrics"][item.factor]) for candidate in eligible}) == 1
            for item in supported
        ):
            selected = min(
                eligible,
                key=lambda candidate: float(
                    candidate["metrics"].get(
                        "distance_m",
                        candidate["route"]["properties"]["total_distance_m"],
                    )
                ),
            )
        else:
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
    supported, _ = _supported_preferences(effective_preferences, candidates)
    avoidance = [item for item in supported if item.direction == "avoid"]
    condition_eligible = [
        candidate for candidate in candidates
        if all(float(candidate["metrics"][item.factor]) <= 0 for item in avoidance)
    ]
    field_review_required = (
        selected is None and bool(supported) and bool(condition_eligible)
        and all(candidate["route"]["properties"].get("unverified_major_road_count", 0) > 0
                for candidate in condition_eligible)
    )
    recommendation_status = (
        "field_review_required" if field_review_required
        else "ready" if selected else "no_supported_preferences"
    )
    recommendation_reason, recommendation_notes = _recommendation_explanation(
        selected, candidates, effective_preferences, unsupported,
        recommendation_status, arguments.departure_time,
    )

    recommendation_id = (
        save_recommendation(arguments.user_id, candidates)
        if arguments.user_id and selected is not None
        else None
    )

    #5. API에 결과 반환
    return {
        "recommendation_id": recommendation_id,
        "selected_route_type": selected["route_type"] if selected else None,
        "selected_route": selected["route"] if selected else None,
        "recommendation_status": recommendation_status,
        "recommendation_reason": recommendation_reason,
        "recommendation_notes": recommendation_notes,
        "candidates": candidates,
        "unsupported_preferences": unsupported,
    }
