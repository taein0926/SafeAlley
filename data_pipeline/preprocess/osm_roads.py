import json
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt, tan
import os
from pathlib import Path
from typing import Any


PEDESTRIAN_FIRST_HIGHWAYS = {
    "footway",
    "living_street",
    "path",
    "pedestrian",
    "residential",
    "service",
    "steps",
    "track",
    "unclassified",
}
MAJOR_ROAD_HIGHWAYS = {
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
}
DENIED_ACCESS = {"no", "private"}
EXPLICIT_FOOT_ACCESS = {"yes", "designated", "permissive", "destination"}
SIDEWALK_ACCESS = {"yes", "both", "left", "right"}


class OsmPreprocessError(RuntimeError):
    """Raised when raw OSM data cannot produce a usable pedestrian graph."""


def _is_walkable(tags: dict[str, str]) -> bool:
    highway = tags.get("highway")
    foot = tags.get("foot")
    if foot in DENIED_ACCESS or tags.get("area") == "yes":
        return False
    if foot in EXPLICIT_FOOT_ACCESS:
        return highway not in {"construction", "proposed"}
    if tags.get("access") in DENIED_ACCESS:
        return False
    if highway == "cycleway":
        return False
    if highway in PEDESTRIAN_FIRST_HIGHWAYS:
        return True
    return highway in MAJOR_ROAD_HIGHWAYS


def _has_pedestrian_evidence(tags: dict[str, str]) -> bool:
    if tags.get("foot", "").lower() in EXPLICIT_FOOT_ACCESS:
        return True
    if tags.get("sidewalk", "").lower() in SIDEWALK_ACCESS:
        return True
    return any(
        tags.get(key, "").lower() in SIDEWALK_ACCESS
        for key in ("sidewalk:left", "sidewalk:right", "sidewalk:both")
    )


def _walkability_factor(tags: dict[str, str]) -> tuple[str, float]:
    highway = tags.get("highway")
    if highway in {"footway", "path", "pedestrian", "steps"}:
        return "pedestrian_only", 1.0
    if highway == "living_street":
        return "living_street", 1.05
    if highway in {"residential", "service", "track", "unclassified"}:
        return "local_road", 1.15
    if highway in MAJOR_ROAD_HIGHWAYS and _has_pedestrian_evidence(tags):
        return "major_road_with_sidewalk", 1.5
    return "major_road_fallback", 4.0


def _sidewalk_status(tags: dict[str, str]) -> str:
    if tags.get("highway") in {"footway", "path", "pedestrian", "living_street"}:
        return "dedicated_or_shared_space"
    values = {
        tags.get(key, "").lower()
        for key in ("sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both")
    }
    if values.intersection(SIDEWALK_ACCESS):
        return "confirmed"
    if "no" in values or "none" in values:
        return "no"
    return "unknown"


def _incline_percent(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    try:
        if text.endswith("%"):
            return abs(float(text[:-1]))
        if text.endswith("°"):
            return abs(tan(radians(float(text[:-1]))) * 100)
        return abs(float(text))
    except ValueError:
        return None


def _walking_directions(tags: dict[str, str]) -> tuple[bool, bool]:
    oneway = tags.get("oneway:foot", "").lower()
    if oneway in {"yes", "true", "1"}:
        return True, False
    if oneway == "-1":
        return False, True
    return True, True


def _default_safety_score() -> float:
    value = float(os.getenv("OSM_DEFAULT_SAFETY_SCORE", "50"))
    if not 0 <= value <= 100:
        raise OsmPreprocessError("OSM_DEFAULT_SAFETY_SCORE must be between 0 and 100")
    return value


def _safety_score_mode() -> str:
    mode = os.getenv("OSM_SAFETY_SCORE_MODE", "uniform").strip().lower()
    if mode not in {"uniform", "demo"}:
        raise OsmPreprocessError(
            "OSM_SAFETY_SCORE_MODE must be either 'uniform' or 'demo'"
        )
    return mode


def safety_score_for_segment(source_id: str, mode: str) -> float:
    if mode == "uniform":
        return _default_safety_score()

    digest = sha256(source_id.encode("utf-8")).digest()
    score_ranges = ((20, 54), (55, 74), (75, 100))
    minimum, maximum = score_ranges[digest[0] % len(score_ranges)]
    return float(minimum + digest[1] % (maximum - minimum + 1))


def _minimum_segment_length_m() -> float:
    value = float(os.getenv("OSM_MIN_SEGMENT_LENGTH_M", "1"))
    if value < 0:
        raise OsmPreprocessError("OSM_MIN_SEGMENT_LENGTH_M cannot be negative")
    return value


def _distance_m(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    longitude_1, latitude_1 = map(radians, first)
    longitude_2, latitude_2 = map(radians, second)
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = longitude_2 - longitude_1
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_008.8 * asin(sqrt(haversine))


def preprocess_osm_roads(input_path: Path, output_path: Path) -> dict[str, int]:
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OsmPreprocessError(f"Cannot read raw OSM file: {input_path}") from exc

    elements = document.get("elements")
    if not isinstance(elements, list):
        raise OsmPreprocessError("Raw OSM document must contain an elements array")

    nodes: dict[int, tuple[float, float]] = {}
    node_tags: dict[int, dict[str, str]] = {}
    ways: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") == "node":
            try:
                node_id = int(element["id"])
                longitude = float(element["lon"])
                latitude = float(element["lat"])
            except (KeyError, TypeError, ValueError):
                continue
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                nodes[node_id] = (longitude, latitude)
                tags = element.get("tags")
                if isinstance(tags, dict):
                    node_tags.setdefault(node_id, {}).update(tags)
        elif element.get("type") == "way":
            ways.append(element)

    safety_score_mode = _safety_score_mode()
    minimum_segment_length = _minimum_segment_length_m()
    features: list[dict[str, Any]] = []
    walkable_way_count = 0
    skipped_edge_count = 0

    for way in ways:
        tags = way.get("tags") or {}
        if not isinstance(tags, dict) or not _is_walkable(tags):
            continue
        node_ids = way.get("nodes")
        if not isinstance(node_ids, list) or len(node_ids) < 2:
            continue

        walkable_way_count += 1
        walkability_class, walkability_factor = _walkability_factor(tags)
        forward_allowed, reverse_allowed = _walking_directions(tags)
        way_id = int(way["id"])
        for edge_index, (source_node_id, target_node_id) in enumerate(
            zip(node_ids, node_ids[1:]),
            start=1,
        ):
            source_coordinate = nodes.get(int(source_node_id))
            target_coordinate = nodes.get(int(target_node_id))
            if (
                source_coordinate is None
                or target_coordinate is None
                or source_coordinate == target_coordinate
                or source_node_id == target_node_id
                or _distance_m(source_coordinate, target_coordinate)
                < minimum_segment_length
            ):
                skipped_edge_count += 1
                continue

            source_id = f"osm-way-{way_id}-edge-{edge_index}"
            safety_score = safety_score_for_segment(source_id, safety_score_mode)
            highway = tags.get("highway")
            crossing_node_ids = [
                int(node_id)
                for node_id in (source_node_id, target_node_id)
                if node_tags.get(int(node_id), {}).get("highway") == "crossing"
            ]
            # A mapped crossing may be a short footway rather than a tagged node.
            # Negative IDs cannot collide with positive OSM node IDs and are shared
            # across all edges of the same crossing way for route-level deduplication.
            if tags.get("footway") == "crossing":
                crossing_node_ids.append(-way_id)
            sidewalk_status = _sidewalk_status(tags)
            properties = {
                "source": "osm",
                "source_id": source_id,
                "name": tags.get("name") or tags.get("name:ko"),
                "source_node_id": int(source_node_id),
                "target_node_id": int(target_node_id),
                "forward_allowed": forward_allowed,
                "reverse_allowed": reverse_allowed,
                "streetlight_score": safety_score,
                "cctv_score": safety_score,
                "population_score": safety_score,
                "safety_data_status": (
                    "demo" if safety_score_mode == "demo" else "unavailable"
                ),
                "osm_way_id": way_id,
                "highway": highway,
                "is_steps": highway == "steps",
                "step_count": tags.get("step_count"),
                "incline": tags.get("incline"),
                "ramp": tags.get("ramp"),
                "wheelchair": tags.get("wheelchair"),
                "handrail": tags.get("handrail"),
                "walkability_class": walkability_class,
                "walkability_factor": walkability_factor,
                "crossing_node_ids": crossing_node_ids,
                "sidewalk_status": sidewalk_status,
                "sidewalk_confirmed": sidewalk_status in {
                    "confirmed",
                    "dedicated_or_shared_space",
                },
                "incline_percent": _incline_percent(tags.get("incline")),
                "osm_tags": tags,
            }
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [source_coordinate, target_coordinate],
                    },
                }
            )

    if not features:
        raise OsmPreprocessError("No walkable road segments were produced")

    stats = {
        "raw_nodes": len(nodes),
        "raw_ways": len(ways),
        "walkable_ways": walkable_way_count,
        "road_segments": len(features),
        "skipped_edges": skipped_edge_count,
    }
    output = {
        "type": "FeatureCollection",
        "name": "michuhol_osm_walkable_roads",
        "metadata": {
            "source": "OpenStreetMap",
            "license": "ODbL-1.0",
            "area_name": os.getenv("OSM_AREA_NAME", "미추홀구"),
            "filter": "pedestrian-accessible highway ways",
            "safety_score_mode": safety_score_mode,
            "stats": stats,
        },
        "features": features,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stats
