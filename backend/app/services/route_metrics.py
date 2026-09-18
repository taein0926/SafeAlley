from collections.abc import Callable
from dataclasses import dataclass


RoutePayload = dict[str, object]
MetricExtractor = Callable[[RoutePayload], float | None]


@dataclass(frozen=True)
class MetricDefinition:
    description: str
    extractor: MetricExtractor


def _properties(route: RoutePayload) -> dict[str, object]:
    properties = route.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Route response has no properties")
    return properties


def _distance(route: RoutePayload) -> float:
    return float(_properties(route)["total_distance_m"])


def _average_safety(route: RoutePayload) -> float | None:
    value = _properties(route).get("average_safety_score")
    return None if value is None else float(value)


def _segment_weighted_average(
    route: RoutePayload,
    field: str,
) -> float | None:
    segments = _properties(route).get("road_segments")
    if not isinstance(segments, list) or not segments:
        return None

    total_distance = 0.0
    weighted_total = 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        distance_value = segment.get("distance_m")
        metric_value = segment.get(field)
        if distance_value is None or metric_value is None:
            return None
        distance = float(distance_value)
        value = float(metric_value)
        total_distance += distance
        weighted_total += value * distance
    return None if total_distance == 0 else weighted_total / total_distance


METRIC_REGISTRY: dict[str, MetricDefinition] = {
    "distance_m": MetricDefinition(
        description="Total route distance in metres",
        extractor=_distance,
    ),
    "safety_score": MetricDefinition(
        description="Distance-weighted composite safety score",
        extractor=_average_safety,
    ),
    "streetlight_score": MetricDefinition(
        description="Distance-weighted streetlight accessibility score",
        extractor=lambda route: _segment_weighted_average(route, "streetlight_score"),
    ),
    "cctv_score": MetricDefinition(
        description="Distance-weighted safety CCTV score",
        extractor=lambda route: _segment_weighted_average(route, "cctv_score"),
    ),
}


def calculate_route_metrics(route: RoutePayload) -> dict[str, float | None]:
    return {
        name: definition.extractor(route)
        for name, definition in METRIC_REGISTRY.items()
    }
