import json
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
import os
from pathlib import Path
from typing import Any


WALKABLE_HIGHWAYS = {
    "footway",
    "living_street",
    "path",
    "pedestrian",
    "primary",
    "primary_link",
    "residential",
    "road",
    "secondary",
    "secondary_link",
    "service",
    "steps",
    "tertiary",
    "tertiary_link",
    "track",
    "unclassified",
}
DENIED_ACCESS = {"no", "private"}
EXPLICIT_FOOT_ACCESS = {"yes", "designated", "permissive", "destination"}


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
    return highway in WALKABLE_HIGHWAYS


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
                "highway": tags.get("highway"),
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
