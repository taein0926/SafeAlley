import json
from pathlib import Path
from typing import Any


REQUIRED_PROPERTIES = {
    "source",
    "source_id",
    "source_node_id",
    "target_node_id",
    "streetlight_score",
    "cctv_score",
    "population_score",
}


def read_road_features(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") != "FeatureCollection":
        raise ValueError("Road document must be a GeoJSON FeatureCollection")

    features = document.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Road document must contain at least one feature")

    source_ids: set[str] = set()
    for feature in features:
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        if geometry.get("type") != "LineString":
            raise ValueError("Every road geometry must be a LineString")
        if not REQUIRED_PROPERTIES.issubset(properties):
            missing = REQUIRED_PROPERTIES.difference(properties)
            raise ValueError(f"Road properties are missing: {sorted(missing)}")

        source_id = str(properties["source_id"])
        if source_id in source_ids:
            raise ValueError(f"Duplicate source_id in document: {source_id}")
        source_ids.add(source_id)

        for score_name in (
            "streetlight_score",
            "cctv_score",
            "population_score",
        ):
            score = properties[score_name]
            if not isinstance(score, (int, float)) or not 0 <= score <= 100:
                raise ValueError(f"Road {source_id} has invalid {score_name}")

        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 2:
            raise ValueError(f"Road {source_id} requires at least two coordinates")
        for longitude, latitude, *_ in coordinates:
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                raise ValueError(f"Road {source_id} contains an invalid WGS84 coordinate")

    return features
