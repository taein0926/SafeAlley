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
from app.services.weather_service import RouteTimeContext, resolve_route_time


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
PROXY_PRIORITY_SUMMARIES = {
    "safety_score": "가로등·CCTV·도움시설 접근성을 함께 고려해",
    "streetlight_score": "가로등과 가까운 정도와 분포를 함께 고려해",
    "cctv_score": "CCTV와 가까운 정도와 분포를 함께 고려해",
}
PROXY_COMPARISONS = {
    "safety_score": (
        "가로등·CCTV·경찰·소방·응급의료 시설 접근성을 종합했을 때"
    ),
    "streetlight_score": (
        "가로등과의 거리·주변 밀도·가로등이 드문 구간을 종합했을 때"
    ),
    "cctv_score": (
        "CCTV와의 거리·주변 밀도·CCTV가 드문 구간을 종합했을 때"
    ),
}
PROXY_EVIDENCE_LABELS = {
    "safety_score": "가로등·CCTV·도움시설 접근성",
    "streetlight_score": "가로등과의 거리·주변 밀도·분포 공백",
    "cctv_score": "CCTV와의 거리·주변 밀도·분포 공백",
}
ROUTE_TYPE_LABELS = {
    "shortest": "빠른 길",
    "balanced": "균형 길",
    "safe": "안전지표 우선 길",
}
CRITERION_LABELS = {
    "distance_m": "거리",
    "safety_score": "안전 관련 시설",
    "streetlight_score": "가로등",
    "cctv_score": "CCTV",
    "crosswalk_count": "횡단보도",
    "intersection_distance_m": "교차로 주변 구간",
    "stairs_distance_m": "계단 구간",
    "sidewalk_coverage_percent": "보행공간",
    "max_slope_percent": "경사",
}
CRITERION_CONFIDENCE = {
    "distance_m": ("high", "도로망 구간 길이를 직접 합산했습니다."),
    "safety_score": (
        "medium",
        "가로등·CCTV·도움시설 공개 좌표를 이용한 상대 비교입니다.",
    ),
    "streetlight_score": (
        "medium",
        "가로등 공개 좌표의 거리·밀도·분포 공백을 이용한 상대 비교입니다.",
    ),
    "cctv_score": (
        "medium",
        "CCTV 공개 좌표의 거리·밀도·분포 공백을 이용한 상대 비교입니다.",
    ),
    "crosswalk_count": ("low", "OSM에 기록된 횡단보도만 집계해 누락될 수 있습니다."),
    "intersection_distance_m": (
        "low",
        "교차로 대표 좌표 주변 35m의 지상 구간을 추정한 값입니다.",
    ),
    "stairs_distance_m": ("low", "OSM에 계단으로 기록된 도로 구간만 합산했습니다."),
    "sidewalk_coverage_percent": (
        "low",
        "OSM에서 보행공간으로 확인된 구간만 계산했습니다.",
    ),
    "max_slope_percent": ("low", "전 구간에 명시된 OSM 경사 정보가 있을 때만 계산합니다."),
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
        "departure_time": arguments.departure_time,
    }


def _is_night(departure_time: time | None) -> bool:
    return departure_time is not None and (
        departure_time >= NIGHT_START or departure_time < NIGHT_END
    )


def _default_preferences(departure_time: time | None, *, is_night: bool | None = None) -> list[RoutePreference]:
    if not (_is_night(departure_time) if is_night is None else is_night):
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
    *, is_night: bool | None = None,
) -> list[RoutePreference]:
    if not (_is_night(departure_time) if is_night is None else is_night):
        return [item for item in preferences if item.factor != "streetlight_score"]
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


def _comparison_candidates(
    selected: dict[str, object] | None,
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
) -> list[dict[str, object]]:
    if selected is None:
        return []
    return [
        candidate for candidate in candidates
        if candidate is not selected
        and candidate["route"]["properties"].get("unverified_major_road_count", 0) == 0
        and _route_identity(candidate) != _route_identity(selected)
        and all(
            candidate["metrics"].get(item.factor) is not None
            and float(candidate["metrics"][item.factor]) <= 0
            for item in preferences if item.direction == "avoid"
        )
    ]


def _comparison_candidate(
    selected: dict[str, object] | None,
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
) -> dict[str, object] | None:
    eligible = _comparison_candidates(selected, candidates, preferences)
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (
            float(item["preference_score"])
            if item["preference_score"] is not None else float("-inf"),
            -float(item["metrics"]["distance_m"]),
        ),
    )


def _metric_tolerance(factor: str, value: float) -> float:
    if factor == "distance_m":
        return max(10.0, value * 0.01)
    if factor in PROXY_FACTORS:
        return 1.0
    if factor in {"crosswalk_count", "stairs_distance_m", "intersection_distance_m",
                  "sidewalk_coverage_percent"}:
        return 0.5
    if factor == "max_slope_percent":
        return 0.1
    return 0.01


def _criterion_value_text(factor: str, value: float) -> str:
    if factor in {"distance_m", "stairs_distance_m", "intersection_distance_m"}:
        return _distance_text(value)
    if factor == "crosswalk_count":
        return f"{value:.0f}개"
    if factor in {"sidewalk_coverage_percent", "max_slope_percent"}:
        return f"{value:.1f}%" if value % 1 else f"{value:.0f}%"
    return f"{value:.1f}"


def _criterion_outcome(
    preference: RoutePreference,
    selected_value: float,
    comparison_value: float,
) -> str:
    difference = selected_value - comparison_value
    tolerance = _metric_tolerance(preference.factor, selected_value)
    if abs(difference) <= tolerance:
        return "similar"
    better = difference > 0 if preference.direction == "maximize" else difference < 0
    return "better" if better else "worse"


def _criterion_summary(
    preference: RoutePreference,
    selected_value: float,
    comparison_value: float | None,
    comparison_label: str | None,
    outcome: str,
) -> str:
    factor = preference.factor
    if comparison_value is None or comparison_label is None:
        if factor in PROXY_FACTORS:
            return "비교할 수 있는 다른 유효 경로가 없어 선택 경로의 시설 조건만 확인했습니다."
        return (
            f"추천 경로 {_criterion_value_text(factor, selected_value)} · "
            "비교할 수 있는 다른 유효 경로가 없습니다."
        )
    if factor in PROXY_FACTORS:
        basis = PROXY_EVIDENCE_LABELS[factor]
        relation = {
            "better": f"추천 경로가 {comparison_label}보다 유리합니다.",
            "similar": f"추천 경로와 {comparison_label}의 조건이 비슷합니다.",
            "worse": f"{comparison_label}이 추천 경로보다 유리합니다.",
        }[outcome]
        return f"{basis}을 종합하면 {relation}"
    relation = {
        "better": "요청 조건에 더 유리",
        "similar": "차이가 거의 없음",
        "worse": "요청 조건에는 불리",
    }[outcome]
    return (
        f"추천 {_criterion_value_text(factor, selected_value)} · "
        f"{comparison_label} {_criterion_value_text(factor, comparison_value)} · {relation}"
    )


def _recommendation_criteria(
    selected: dict[str, object] | None,
    comparison: dict[str, object] | None,
    preferences: list[RoutePreference],
    unsupported: list[UnsupportedPreference],
    *, is_night: bool = True,
) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    unsupported_factors = {item.factor for item in unsupported}
    comparison_label = (
        ROUTE_TYPE_LABELS.get(str(comparison["route_type"]), "비교 경로")
        if comparison else None
    )
    if selected is None:
        for preference in preferences:
            if preference.factor in unsupported_factors:
                continue
            confidence, confidence_reason = CRITERION_CONFIDENCE.get(
                preference.factor,
                ("low", "검증된 품질 기준이 등록되지 않은 조건입니다."),
            )
            details.append({
                "factor": preference.factor,
                "label": CRITERION_LABELS.get(
                    preference.factor, preference.factor.replace("_", " ")
                ),
                "outcome": "unavailable",
                "summary": "추천 경로가 확정되지 않아 조건별 비교를 표시하지 않습니다.",
                "confidence": confidence,
                "confidence_reason": confidence_reason,
            })
    if selected is not None:
        for preference in preferences:
            if preference.factor in unsupported_factors:
                continue
            value = selected["metrics"].get(preference.factor)
            if value is None:
                continue
            other = comparison["metrics"].get(preference.factor) if comparison else None
            outcome = (
                _criterion_outcome(preference, float(value), float(other))
                if other is not None else "not_compared"
            )
            confidence, confidence_reason = CRITERION_CONFIDENCE.get(
                preference.factor,
                ("low", "검증된 품질 기준이 등록되지 않은 조건입니다."),
            )
            details.append({
                "factor": preference.factor,
                "label": CRITERION_LABELS.get(
                    preference.factor, preference.factor.replace("_", " ")
                ),
                "outcome": outcome,
                "summary": _criterion_summary(
                    preference,
                    float(value),
                    float(other) if other is not None else None,
                    comparison_label,
                    outcome,
                ),
                "confidence": confidence,
                "confidence_reason": confidence_reason,
            })
    for item in unsupported:
        confidence_reason = (
            "요청을 만족하는 경로 후보가 없습니다."
            if "hard avoidance" in item.reason
            else "검증 가능한 측정값이 없어 비교하지 못했습니다."
        )
        details.append({
            "factor": item.factor,
            "label": CRITERION_LABELS.get(item.factor, item.factor.replace("_", " ")),
            "outcome": "unavailable",
            "summary": "자료가 부족해 추천 조건에 반영하지 않았습니다.",
            "confidence": "low",
            "confidence_reason": confidence_reason,
        })
    if not is_night:
        for detail in details:
            if detail["factor"] == "safety_score":
                for field in ("summary", "confidence_reason"):
                    detail[field] = detail[field].replace("가로등·CCTV", "CCTV")
            elif detail["factor"] == "streetlight_score" and any(
                item.factor == "streetlight_score" and item.reason == "Excluded during daylight"
                for item in unsupported
            ):
                detail["summary"] = "낮에는 가로등 조건을 추천 순위에 반영하지 않습니다."
                detail["confidence_reason"] = "낮 시간 가로등 제외 정책을 적용했습니다."
    return details


def _secondary_condition_sentence(
    preference: RoutePreference,
    selected: dict[str, object],
    comparison: dict[str, object],
    comparison_label: str = "다른 길",
) -> str | None:
    factor = preference.factor
    chosen = selected["metrics"].get(factor)
    other = comparison["metrics"].get(factor)
    if chosen is None or other is None:
        return None
    difference = float(chosen) - float(other)
    if factor == "stairs_distance_m" and preference.direction == "avoid":
        if float(chosen) == 0 and float(other) == 0:
            return "두 경로 모두 지도에 기록된 계단 구간은 0m예요."
        return "선택한 길의 지도상 계단 구간은 0m예요."
    if factor == "stairs_distance_m":
        if abs(difference) < 0.5:
            return "두 경로의 지도상 계단 구간 길이는 같아요."
        relation = "짧아요" if difference < 0 else "길어요"
        return f"지도에 기록된 계단 구간은 {comparison_label}보다 약 {abs(difference):.0f}m {relation}"
    if factor == "crosswalk_count":
        if difference == 0:
            return "두 경로의 지도상 횡단보도 수는 같아요."
        direction = "적어요" if difference < 0 else "많아요"
        return f"지도에 기록된 횡단보도는 {comparison_label}보다 {abs(difference):.0f}개 {direction}"
    if factor == "sidewalk_coverage_percent":
        if abs(difference) < 0.5:
            return "확인된 보행공간 비율은 두 경로가 거의 같아요."
        direction = "높아요" if difference > 0 else "낮아요"
        return f"확인된 보행공간 비율은 {comparison_label}보다 {abs(difference):.0f}%p {direction}"
    if factor == "intersection_distance_m":
        if abs(difference) < 0.5:
            return "교차로 주변으로 추정된 구간 길이는 두 경로가 같아요."
        relation = "짧아요" if difference < 0 else "길어요"
        return f"교차로 주변으로 추정된 구간은 {comparison_label}보다 약 {abs(difference):.0f}m {relation}"
    if factor == "max_slope_percent":
        if abs(difference) < 0.1:
            return "지도에 기록된 최대 경사는 두 경로가 거의 같아요."
        relation = "낮아요" if difference < 0 else "높아요"
        return f"지도에 기록된 최대 경사는 {comparison_label}보다 {abs(difference):.1f}%p {relation}"
    if factor in PROXY_FACTORS:
        if abs(difference) <= 1:
            return None
        subject = PROXY_EVIDENCE_LABELS[factor]
        if difference > 0:
            return f"{subject}을 종합하면 이 길이 더 유리해요."
        return f"다만 {subject}만 보면 {comparison_label}이 더 유리해요."
    return None


def _metric_evidence_note(
    preference: RoutePreference,
    selected: dict[str, object],
    comparison: dict[str, object],
    comparison_label: str = "비교 경로",
) -> str | None:
    factor = preference.factor
    chosen = selected["metrics"].get(factor)
    other = comparison["metrics"].get(factor)
    if chosen is None or other is None:
        return None
    chosen_value, other_value = float(chosen), float(other)
    if factor == "distance_m":
        if abs(chosen_value - other_value) < 10:
            return (
                f"거리: 추천 경로 {chosen_value:.1f}m, "
                f"{comparison_label} {other_value:.1f}m."
            )
        return (
            f"거리: 추천 경로 {_distance_text(chosen_value)}, "
            f"{comparison_label} {_distance_text(other_value)}."
        )
    if factor == "stairs_distance_m":
        return f"지도상 계단 구간: 추천 경로 {chosen_value:.0f}m, {comparison_label} {other_value:.0f}m."
    if factor == "crosswalk_count":
        return f"OSM 횡단보도 기록: 추천 경로 {chosen_value:.0f}개, {comparison_label} {other_value:.0f}개."
    if factor == "sidewalk_coverage_percent":
        return f"확인된 보행공간 비율: 추천 경로 {chosen_value:.0f}%, {comparison_label} {other_value:.0f}%."
    if factor == "intersection_distance_m":
        return (
            "교차로 주변으로 추정된 구간: "
            f"추천 경로 {chosen_value:.0f}m, {comparison_label} {other_value:.0f}m."
        )
    if factor == "max_slope_percent":
        return (
            "지도에 기록된 최대 경사: "
            f"추천 경로 {chosen_value:.1f}%, {comparison_label} {other_value:.1f}%."
        )
    if factor in PROXY_FACTORS:
        label = PROXY_EVIDENCE_LABELS[factor]
        if chosen_value == other_value:
            return f"{label}: 두 경로의 조건이 같습니다."
        relation = (
            "추천 경로가 더 유리합니다"
            if chosen_value > other_value else f"{comparison_label}이 더 유리합니다"
        )
        return f"{label}: {relation}."
    return None


def _recommendation_explanation(
    selected: dict[str, object] | None,
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
    unsupported: list[UnsupportedPreference],
    status: str,
    departure_time: time | None,
    *, is_night: bool | None = None,
) -> tuple[str, list[str]]:
    night = _is_night(departure_time) if is_night is None else is_night
    priorities = PROXY_PRIORITY_SUMMARIES if night else {
        **PROXY_PRIORITY_SUMMARIES, "safety_score": "CCTV·도움시설 접근성을 함께 고려해",
    }
    comparisons = PROXY_COMPARISONS if night else {
        **PROXY_COMPARISONS,
        "safety_score": "CCTV·도움시설(경찰·소방·응급의료) 접근성을 종합했을 때",
    }
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
        if primary.factor in PROXY_PRIORITY_SUMMARIES:
            summary = (
                f"{priorities[primary.factor]} "
                f"약 {_distance_text(distance)} 길을 추천했어요."
            )
        else:
            summary = f"{priority} 약 {_distance_text(distance)} 길을 골랐어요."
        eligible = _comparison_candidates(selected, candidates, supported)
        comparison = _comparison_candidate(selected, candidates, supported)
        if comparison is not None:
            comparison_label = ROUTE_TYPE_LABELS.get(
                str(comparison["route_type"]), "비교 경로"
            )
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
                    summary += f" {comparison_label}보다 약 {difference:.0f}m 짧아요."
                elif difference < -max(10, distance * 0.01):
                    summary += (
                        f" {comparison_label}보다 약 {-difference:.0f}m 더 걸리지만, "
                        "다른 요청 조건도 함께 반영했어요."
                    )
                elif abs(difference) > 0.5:
                    summary += (
                        f" {comparison_label}과의 거리 차이는 "
                        f"약 {abs(difference):.0f}m로 거의 같아요."
                    )
            else:
                chosen_value = selected["metrics"].get(primary.factor)
                other_value = comparison["metrics"].get(primary.factor)
                if chosen_value is not None and other_value is not None:
                    change = float(chosen_value) - float(other_value)
                    threshold = 0 if primary.factor == "crosswalk_count" else 1
                    better = (
                        change > threshold if primary.direction == "maximize"
                        else change < -threshold
                    )
                    if better:
                        if primary.factor in PROXY_PRIORITY_SUMMARIES:
                            summary = (
                                f"{comparisons[primary.factor]} "
                                f"{comparison_label}보다 조건이 좋아 "
                                "이 길을 추천했어요."
                            )
                        elif primary.factor == "crosswalk_count":
                            direction = "적어" if change < 0 else "많아"
                            summary = (
                                f"지도에 기록된 횡단보도가 {comparison_label}보다 "
                                f"{abs(change):.0f}개 {direction} 이 길을 추천했어요."
                            )
                        elif primary.factor == "sidewalk_coverage_percent":
                            direction = "높아" if change > 0 else "낮아"
                            summary = (
                                f"확인된 보행공간 비율이 {comparison_label}보다 "
                                f"{abs(change):.0f}%p {direction} 이 길을 추천했어요."
                            )
                        elif primary.factor == "stairs_distance_m":
                            summary = (
                                f"지도에 기록된 계단 구간이 {comparison_label}보다 "
                                f"약 {abs(change):.0f}m 짧아 이 길을 추천했어요."
                            )
                        elif primary.factor == "intersection_distance_m":
                            summary = (
                                f"교차로 주변으로 추정된 구간이 {comparison_label}보다 "
                                f"약 {abs(change):.0f}m 짧아 이 길을 추천했어요."
                            )
                        elif primary.factor == "max_slope_percent":
                            summary = (
                                f"지도에 기록된 최대 경사가 {comparison_label}보다 "
                                f"{abs(change):.1f}%p 낮아 이 길을 추천했어요."
                            )
                        else:
                            metric_name = METRIC_NAMES.get(primary.factor, "요청 조건")
                            direction = "높아요" if primary.direction == "maximize" else "낮아요"
                            advantage = f"{comparison_label}보다 {metric_name} 값이 더 {direction}"
                            summary += f" {advantage}"
            if primary.factor != "distance_m":
                if difference < -0.5:
                    summary += f" {comparison_label}보다 약 {-difference:.0f}m 더 걸어요."
                elif difference > 0.5 and len(primary_values) > 1:
                    summary += f" 거리도 약 {difference:.0f}m 짧아요."
            secondary = sorted(
                (
                    item for item in supported
                    if item.factor not in {primary.factor, "distance_m"}
                ),
                key=lambda item: item.weight,
                reverse=True,
            )
            if secondary:
                detail = _secondary_condition_sentence(
                    secondary[0], selected, comparison, comparison_label,
                )
                if detail:
                    summary += f" {detail}"
            for item in supported:
                evidence = _metric_evidence_note(
                    item, selected, comparison, comparison_label,
                )
                if evidence:
                    notes.append(evidence)
        for item in supported:
            value = selected["metrics"].get(item.factor)
            if value != 0:
                continue
            if item.factor == "crosswalk_count":
                notes.append("횡단보도 0개는 OSM에 기록된 지점이 없다는 뜻이며, 실제 부재를 확인한 것은 아닙니다.")
            elif item.factor == "sidewalk_coverage_percent":
                notes.append("보행공간 비율 0%는 지도에서 보행공간으로 확인된 구간이 없다는 뜻이며, 실제 보도가 없다는 뜻은 아닙니다.")
            elif item.factor == "stairs_distance_m":
                notes.append("계단 구간 0m는 지도에 기록된 계단이 없다는 뜻이며, 현장에 계단이 없음을 보장하지 않습니다.")
        if excluded:
            notes.append(
                f"다른 길 {len(excluded)}개는 큰 도로의 보행로 정보가 없어 추천에서 뺐어요."
            )
        if night and any(item.factor in PROXY_FACTORS for item in supported):
            notes.append("밤 시간 질문으로 처리했지만, 가로등 점등 상태나 CCTV 작동 여부는 알 수 없습니다.")
        if any(item.factor in PROXY_FACTORS for item in supported):
            notes.append("지도에 등록된 시설 위치만 비교했습니다. 실제 치안이나 안전을 보장하지 않습니다.")
    for item in unsupported:
        label = METRIC_NAMES.get(item.factor, item.factor.replace("_", " "))
        if item.reason == "Excluded during daylight":
            notes.append("낮에는 요청한 가로등 조건을 추천 순위에 반영하지 않았습니다.")
        elif item.factor == "max_slope_percent":
            notes.append("경사는 전 구간 측정 자료가 없어 추천 조건에 반영하지 않았습니다. DEM은 현재 적재되지 않았습니다.")
        elif "hard avoidance" in item.reason:
            notes.append(f"{label} 요청을 충족하는 후보가 없어 해당 조건을 반영하지 않았습니다.")
        else:
            notes.append(f"{label} 요청은 검증된 측정값이 없어 반영하지 않았습니다.")
    if not night:
        notes = [note.replace("가로등·CCTV", "CCTV") for note in notes]
        notes.append("낮 시간에는 가로등을 제외하고 CCTV·도움시설 위치만으로 안전 관련 지표를 계산했습니다.")
    notes.append("지도 자료만으로 실제 길 상태나 통행 가능 여부를 보장할 수 없습니다.")
    return summary, notes


def generate_route_candidates(
    arguments: RouteOptimizationArguments,
    *, time_context: RouteTimeContext | None = None,
) -> list[dict[str, object]]:
    """Generate route alternatives independently from preference scoring."""

    route_arguments = _route_arguments(arguments)
    route_arguments["time_context"] = time_context or resolve_route_time(arguments.departure_time)
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


def _recommendation_factors(selected, preferences, unsupported, arguments) -> list[str]:
    """Structured, evaluated conditions for UI icons; never infer from LLM prose."""
    if selected is None:
        return []
    excluded = {item.factor for item in unsupported}
    factors = set()
    for item in preferences:
        if item.factor in excluded or selected["metrics"].get(item.factor) is None:
            continue
        if item.factor == "distance_m" and item.direction == "minimize":
            factors.add("distance")
        elif item.factor in PROXY_FACTORS and item.direction == "maximize":
            factors.add("safety")
        elif item.factor == "stairs_distance_m" and item.direction in {"minimize", "avoid"}:
            factors.add("stairs")
        elif item.factor == "intersection_distance_m" and item.direction in {"minimize", "avoid"}:
            factors.add("intersection")
    if arguments.stairs_weight > 0:
        factors.add("stairs")
    if arguments.intersection_weight > 0 and selected["route"]["properties"].get("intersection_data_available"):
        factors.add("intersection")
    return [factor for factor in ("distance", "safety", "stairs", "intersection") if factor in factors]


def rank_route_candidates(arguments: RouteOptimizationArguments) -> dict[str, object]:
    time_context = resolve_route_time(arguments.departure_time)
    #1. 최단 경로와 안전 경로 후보 생성
    candidates = generate_route_candidates(arguments, time_context=time_context)
    #2. 사용자 조건이없으면 시간대별 기본 조건 사용
    if arguments.preferences:
        requested_preferences = arguments.preferences
    elif arguments.user_id:
        requested_preferences = learned_preferences_for_ranking(arguments.user_id)
        if not requested_preferences:
            requested_preferences = _default_preferences(arguments.departure_time, is_night=time_context.is_night)
    else:
        requested_preferences = _default_preferences(arguments.departure_time, is_night=time_context.is_night)
    #3. 야간이면 안전 관련 가중치 적용
    effective_preferences = _apply_time_policy(
        requested_preferences,
        arguments.departure_time,
        is_night=time_context.is_night,
    )
    daytime_ignored = [
        UnsupportedPreference(factor=item.factor, reason="Excluded during daylight")
        for item in requested_preferences
        if not time_context.is_night and item.factor == "streetlight_score"
    ]
    if not effective_preferences:
        effective_preferences = _default_preferences(arguments.departure_time, is_night=time_context.is_night)
    #4. 후보 경로 점수 계산 및 최종 경로 선택
    selected, unsupported = rank_generated_candidates(
        candidates,
        effective_preferences,
    )
    unsupported.extend(daytime_ignored)
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
        is_night=time_context.is_night,
    )
    unsupported_factors = {item.factor for item in unsupported}
    explanation_preferences = [
        item for item in supported if item.factor not in unsupported_factors
    ]
    comparison = _comparison_candidate(
        selected, candidates, explanation_preferences,
    )
    recommendation_criteria = _recommendation_criteria(
        selected, comparison, effective_preferences, unsupported,
        is_night=time_context.is_night,
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
        "recommendation_factors": _recommendation_factors(
            selected, effective_preferences, unsupported, arguments,
        ),
        "compared_route_type": comparison["route_type"] if comparison else None,
        "recommendation_criteria": recommendation_criteria,
        "candidates": candidates,
        "unsupported_preferences": unsupported,
    }
