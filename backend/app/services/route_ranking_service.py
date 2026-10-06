from datetime import time

from app.schemas.agent import (
    RouteOptimizationArguments,
    RoutePreference,
    UnsupportedPreference,
)
from app.services.route_metrics import METRIC_REGISTRY, calculate_route_metrics
from app.services.route_progress import ProgressCallback, candidate_report, comparison_reports, report
from app.services.route_service import (
    get_custom_route,
    RouteNotFoundError,
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
    "crosswalk_count": "OSM 건널목 구간을 줄이는 조건으로",
    "stairs_distance_m": "지도에 표시된 계단 구간을 피하는 조건으로",
    "sidewalk_coverage_percent": "지도에 표시된 보행공간을 참고해",
    "max_slope_percent": "지도에 기록된 경사를 참고해",
}
METRIC_NAMES = {
    "distance_m": "거리",
    "safety_score": "안전 관련 시설 지표",
    "streetlight_score": "가로등 위치 지표",
    "cctv_score": "CCTV 위치 지표",
    "crosswalk_count": "건널목 수",
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
    "shortest": "최단 경로",
    "balanced": "이전 경로",
    "safe": "이전 경로",
    "custom": "맞춤 경로",
}
CRITERION_LABELS = {
    "distance_m": "거리",
    "safety_score": "안전 관련 시설",
    "streetlight_score": "가로등",
    "cctv_score": "CCTV",
    "crosswalk_count": "건널목 회피",
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
    "crosswalk_count": ("low", "OSM에 기록된 건널목만 집계해 누락될 수 있습니다."),
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
        if preference.factor not in METRIC_REGISTRY or preference.factor == "intersection_distance_m":
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
        and all(candidate["metrics"].get(p.factor) is not None for p in preferences)
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
    if factor in {"crosswalk_count", "stairs_distance_m",
                  "sidewalk_coverage_percent"}:
        return 0.5
    if factor == "max_slope_percent":
        return 0.1
    return 0.01


def _criterion_value_text(factor: str, value: float) -> str:
    if factor in {"distance_m", "stairs_distance_m"}:
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
    *, is_night: bool = True,
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
            return "두 경로의 지도상 건널목 수는 같아요."
        direction = "적어요" if difference < 0 else "많아요"
        return f"지도에 기록된 건널목은 {comparison_label}보다 {abs(difference):.0f}개 {direction}"
    if factor == "sidewalk_coverage_percent":
        if abs(difference) < 0.5:
            return "확인된 보행공간 비율은 두 경로가 거의 같아요."
        direction = "높아요" if difference > 0 else "낮아요"
        return f"확인된 보행공간 비율은 {comparison_label}보다 {abs(difference):.0f}%p {direction}"
    if factor == "max_slope_percent":
        if abs(difference) < 0.1:
            return "지도에 기록된 최대 경사는 두 경로가 거의 같아요."
        relation = "낮아요" if difference < 0 else "높아요"
        return f"지도에 기록된 최대 경사는 {comparison_label}보다 {abs(difference):.1f}%p {relation}"
    if factor in PROXY_FACTORS:
        if abs(difference) <= 1:
            return None
        subject = ("CCTV·도움시설 접근성" if factor == "safety_score" and not is_night
                   else PROXY_EVIDENCE_LABELS[factor])
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
        return f"OSM 건널목 기록: 추천 경로 {chosen_value:.0f}개, {comparison_label} {other_value:.0f}개."
    if factor == "sidewalk_coverage_percent":
        return f"확인된 보행공간 비율: 추천 경로 {chosen_value:.0f}%, {comparison_label} {other_value:.0f}%."
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
    elif not any(p.factor not in {u.factor for u in unsupported} for p in preferences):
        distance = float(selected["metrics"]["distance_m"])
        summary = f"등록된 건널목과 인도 정보를 탐색 비용에 반영해 약 {_distance_text(distance)} 길을 골랐어요. 일부 구간의 건널목 수는 확인할 수 없어요."
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
                    premise = "비교한 경로 모두 지도 자료상 건널목 수가 0개여서"
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
                        f" 비교 경로({comparison_label})와의 거리 차이는 "
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
                                f"지도에 기록된 건널목이 {comparison_label}보다 "
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
                    secondary[0], selected, comparison, comparison_label, is_night=night,
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
                notes.append("건널목 0개는 OSM에 기록된 지점이 없다는 뜻이며, 실제 부재를 확인한 것은 아닙니다.")
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
        elif item.factor == "crosswalk_count":
            notes.append(
                "일부 구간의 인도·횡단 연결 정보가 없어 건널목 수를 비교할 수 없습니다. "
                "경로 탐색에 건널목 비용을 사용했더라도 추천 근거로 삼지 않았습니다."
            )
        elif item.factor == "max_slope_percent":
            notes.append("경사는 전 구간 측정 자료가 없어 추천 조건에 반영하지 않았습니다. DEM은 현재 적재되지 않았습니다.")
        elif "hard avoidance" in item.reason:
            notes.append(f"{label} 요청을 충족하는 후보가 없어 해당 조건을 반영하지 않았습니다.")
        else:
            notes.append(f"{label} 요청은 검증된 측정값이 없어 반영하지 않았습니다.")
    if not night:
        notes = [note.replace("가로등·CCTV", "CCTV") for note in notes]
        notes.append("낮 시간에는 가로등을 제외하고 CCTV·도움시설 위치만으로 안전 관련 지표를 계산했습니다.")
    if selected is not None and selected["route"]["properties"].get("centreline_fallback_distance_m", 0) > 0:
        notes.append("OSM에 분리된 인도가 없는 일부 구간은 기존 도로망을 사용하며 실제 횡단 횟수는 미확인입니다.")
    notes.append("지도 자료만으로 실제 길 상태나 통행 가능 여부를 보장할 수 없습니다.")
    return summary, notes


def generate_route_candidates(
    arguments: RouteOptimizationArguments,
    *, time_context: RouteTimeContext | None = None,
    preferences: list[RoutePreference] | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[dict[str, object]]:
    """Generate a distance baseline and a request-aware route on one shared graph."""

    route_arguments = _route_arguments(arguments)
    route_arguments["time_context"] = time_context or resolve_route_time(arguments.departure_time)
    report(on_progress, "graph", "출발지·도착지를 도로망에 연결하고 보행 경로를 계산할 자료를 읽고 있어요.", "working")
    route_arguments["prepared"] = prepare_route(
        start_longitude=arguments.origin.longitude,
        start_latitude=arguments.origin.latitude,
        end_longitude=arguments.destination.longitude,
        end_latitude=arguments.destination.latitude,
        source=arguments.source,
    )
    report(on_progress, "graph", "도로망 연결을 확인했어요. 같은 도로망에서 최단 후보와 요청 조건을 반영한 후보를 찾을게요.")
    # Baseline is unaffected by sliders. Both paths use the same OSM graph/snaps.
    baseline_arguments = {**route_arguments, "stairs_weight": 0.0, "intersection_weight": 0.0}
    active_preferences = preferences if preferences is not None else arguments.preferences
    report(on_progress, "candidate-shortest", "비교 기준이 될 최단 후보를 찾고 있어요.", "working")
    shortest_route = get_shortest_route(**baseline_arguments)

    def candidate(route, baseline=None):
        value = {"route_type": route["properties"]["route_type"], "preference_score": None,
                 "metrics": calculate_route_metrics(route), "route": route}
        if baseline is not None and _route_identity(value) == _route_identity(baseline):
            report(on_progress, f"candidate-{value['route_type']}", "요청 조건을 반영해 계산해도 최단 후보와 같은 동선이에요. 별도의 다른 길은 나오지 않았어요.")
        else:
            candidate_report(on_progress, value, active_preferences)
        return value

    candidates = [candidate(shortest_route)]
    report(on_progress, "candidate-custom", "말씀하신 조건을 반영해 다른 경로를 찾고 있어요.", "working")
    try:
        candidates.append(candidate(get_custom_route(
            **route_arguments, preferences=preferences if preferences is not None else arguments.preferences,
            crossing_weight=arguments.crossing_weight,
        ), baseline=candidates[0]))
    except RouteNotFoundError:
        # A hard avoidance request must not silently fall back to a violating path.
        report(on_progress, "candidate-custom", "회피 조건을 충족하는 맞춤 후보를 찾지 못했어요. 이 조건은 완화하지 않겠습니다.", "unavailable")
    return candidates


def rank_generated_candidates(
    candidates: list[dict[str, object]],
    preferences: list[RoutePreference],
) -> tuple[dict[str, object] | None, list[UnsupportedPreference]]:
    """Score already-generated alternatives using only complete metric data."""

    hard = [p for p in preferences if p.direction == "avoid"]
    constrained = [c for c in candidates if all(c["metrics"].get(p.factor) is not None and c["metrics"][p.factor] <= 0 for p in hard)]
    if hard and constrained:
        candidates = constrained
    supported, unsupported = _supported_preferences(preferences, candidates)
    if any(p.direction == "avoid" and p.factor not in {s.factor for s in supported} for p in preferences):
        return None, unsupported

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
        # Ranking must not undo the walking-network priority used during search.
        outside = [c["route"]["properties"].get("nonpreferred_walking_distance_m") for c in eligible]
        if outside and all(value is not None for value in outside):
            minimum = min(outside)
            eligible = [c for c in eligible if c["route"]["properties"]["nonpreferred_walking_distance_m"] <= minimum + .001]
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
        elif item.factor == "crosswalk_count" and item.direction in {"minimize", "avoid"}:
            factors.add("crossing")
    if arguments.stairs_weight > 0:
        factors.add("stairs")
    properties = selected["route"]["properties"]
    if ("crosswalk_count" not in excluded
        and properties.get("crossing_data_available")
        and (arguments.crossing_weight > 0
             or properties.get("cost_weights", {}).get("crossing", 0) > 0)):
        factors.add("crossing")
    return [factor for factor in ("distance", "safety", "stairs", "crossing") if factor in factors]


def rank_route_candidates(arguments: RouteOptimizationArguments, *, on_progress: ProgressCallback | None = None) -> dict[str, object]:
    time_context = resolve_route_time(arguments.departure_time)
    #2. 사용자 조건이없으면 시간대별 기본 조건 사용
    if arguments.preferences:
        requested_preferences = arguments.preferences
    elif arguments.user_id:
        requested_preferences = learned_preferences_for_ranking(arguments.user_id)
        if not requested_preferences:
            requested_preferences = _default_preferences(arguments.departure_time, is_night=time_context.is_night)
    else:
        requested_preferences = _default_preferences(arguments.departure_time, is_night=time_context.is_night)
    requested_preferences = list(requested_preferences)
    present = {p.factor for p in requested_preferences}
    for factor, strength in (("stairs_distance_m", arguments.stairs_weight), ("crosswalk_count", arguments.crossing_weight)):
        if strength > 0 and factor not in present:
            requested_preferences.append(RoutePreference(factor=factor, direction="minimize", weight=strength * 100))
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
    for item in daytime_ignored:
        report(on_progress, f"policy-{item.factor}", "출발 시각이 낮이라 가로등 우선 조건은 이번 경로 계산에서 제외했어요.")
    candidates = generate_route_candidates(arguments, time_context=time_context, preferences=effective_preferences, on_progress=on_progress)
    comparison_reports(on_progress, candidates, effective_preferences)
    #4. 후보 경로 점수 계산 및 최종 경로 선택
    selected, unsupported = rank_generated_candidates(
        candidates,
        effective_preferences,
    )
    # The custom path optimizes the request during search, not a candidate-relative
    # min/max score that changes whenever a hidden alternative is added.
    custom = next((c for c in candidates if c["route_type"] == "custom"), None)
    if custom is not None:
        supported_for_custom, _ = _supported_preferences(effective_preferences, [custom])
        properties = custom["route"]["properties"]
        custom_objective = any(
            p.factor != "distance_m" and p.factor not in {u.factor for u in unsupported}
            for p in supported_for_custom
        )
        hard_conditions_met = all(
            custom["metrics"].get(p.factor) is not None and custom["metrics"][p.factor] <= 0
            for p in effective_preferences if p.direction == "avoid"
        )
        selected_outside = selected["route"]["properties"].get("nonpreferred_walking_distance_m") if selected else None
        custom_outside = properties.get("nonpreferred_walking_distance_m")
        walking_priority_met = (selected_outside is None or custom_outside is None
                                or custom_outside <= selected_outside + .001)
        if custom_objective and hard_conditions_met and walking_priority_met and properties.get("unverified_major_road_count", 0) == 0:
            selected = custom
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
    if selected:
        name = "최단 후보" if selected["route_type"] == "shortest" else "맞춤 후보"
        report(on_progress, "selection", f"적용 가능한 조건을 종합해 {name}를 선택했어요. 추천 이유와 경로를 정리하고 있어요.")
    else:
        report(on_progress, "selection", "후보 비교는 마쳤지만 추천 조건을 충족하지 못했어요. 확인이 필요한 내용을 정리하고 있어요.", "unavailable")
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
