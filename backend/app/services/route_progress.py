"""Observable routing milestones and measurements, delivered as work completes."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from app.repositories.safety_repository import SafetyRepositoryError, count_route_facilities
from app.services.route_metrics import METRIC_REGISTRY

ProgressCallback = Callable[[dict], None]
LABELS = {
    "distance_m": "거리", "streetlight_score": "가로등", "cctv_score": "CCTV",
    "stairs_distance_m": "계단 구간", "crosswalk_count": "건널목",
    "safety_score": "안전시설 지표", "sidewalk_coverage_percent": "보행공간 비율",
}


def report(callback: ProgressCallback | None, update_id: str, message: str, state: str = "completed") -> None:
    if callback:
        callback({"id": update_id, "message": message, "state": state})


def candidate_report(callback: ProgressCallback | None, candidate: dict, preferences: list) -> None:
    if not callback:
        return
    route_type = candidate["route_type"]
    label = "최단 후보" if route_type == "shortest" else "맞춤 후보"
    distance = candidate["metrics"]["distance_m"]
    report(callback, f"candidate-{route_type}", f"{label}를 찾았어요. 도로망 기준 약 {distance:.0f}m예요.")
    requested = {p.factor for p in preferences}
    if requested.intersection({"streetlight_score", "cctv_score", "safety_score"}):
        categories = []
        if requested.intersection({"streetlight_score", "safety_score"}):
            categories.append(("streetlights", "가로등"))
        if requested.intersection({"cctv_score", "safety_score"}):
            categories.append(("cctvs", "CCTV"))
        names = "·".join(name for _, name in categories)
        report(callback, f"facilities-{route_type}", f"{label} 주변의 {names} 등록 위치를 확인하고 있어요.", "working")
        try:
            counts = count_route_facilities(candidate["route"]["geometry"])
            detail = ", ".join(f"{name} 위치 {counts[key]}곳" for key, name in categories)
            report(callback, f"facilities-{route_type}", f"{label} 주변 30m에 등록된 {detail}을 확인했어요.")
        except SafetyRepositoryError:
            report(callback, f"facilities-{route_type}",
                   f"{label} 주변 시설 수는 확인하지 못했어요. 경로 계산은 기존 위치 지표로 계속합니다.", "unavailable")


def comparison_reports(callback: ProgressCallback | None, candidates: list[dict], preferences: list) -> None:
    if not callback:
        return
    for preference in preferences:
        factor = preference.factor
        if factor not in METRIC_REGISTRY:
            continue
        label = LABELS.get(factor, factor)
        last_letter = ord(label[-1])
        object_label = label + ("을" if 0xAC00 <= last_letter <= 0xD7A3 and (last_letter - 0xAC00) % 28 else "를")
        values = [(c["route_type"], c["metrics"].get(factor)) for c in candidates]
        if not values or any(value is None for _, value in values):
            report(callback, f"compare-{factor}", f"{label}은 후보별 자료가 충분하지 않아 비교에 반영할 수 없어요.", "unavailable")
            continue
        parts = []
        for route_type, value in values:
            name = "최단 후보" if route_type == "shortest" else "맞춤 후보"
            if factor in {"distance_m", "stairs_distance_m"}:
                formatted = f"약 {value:.0f}m"
            elif factor == "crosswalk_count":
                formatted = f"OSM 기록 {value:.0f}개"
            elif factor == "sidewalk_coverage_percent":
                formatted = f"{value:.1f}%"
            else:
                formatted = f"위치 지표 {value:.1f}"
            parts.append(f"{name} {formatted}")
        detail = "기록된 계단 구간이 없는 후보만 추천 대상으로 확인해요. " if factor == "stairs_distance_m" and preference.direction == "avoid" else ""
        if len(values) == 1:
            detail = "맞춤 후보가 없어 이 후보의 기록만 확인했어요."
        elif len({value for _, value in values}) == 1:
            detail += "두 후보의 값이 같아요."
        else:
            best = (max if preference.direction == "maximize" else min)(value for _, value in values)
            names = ["최단 후보" if route_type == "shortest" else "맞춤 후보" for route_type, value in values if value == best]
            detail += f"이 조건에서는 {'·'.join(names)}가 더 유리해요."
        report(callback, f"compare-{factor}", f"{object_label} 비교했어요. {', '.join(parts)}. {detail}")


def iter_workflow_progress(action: Callable) -> Iterator[dict]:
    """Run routing once while yielding real callbacks immediately."""
    queue: Queue = Queue()

    def run() -> None:
        try:
            result = action(lambda data: queue.put({"type": "route_progress", "data": data}))
            queue.put({"type": "routing_result", "data": result})
        except Exception as exc:
            queue.put({"type": "routing_error", "error": exc})

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="route-progress") as executor:
        executor.submit(run)
        while True:
            event = queue.get()
            if event["type"] == "routing_error":
                raise event["error"]
            yield event
            if event["type"] == "routing_result":
                return
