"""Validate the supplied WGS84 point references, without inventing road edges."""
import json
from math import isfinite
from pathlib import Path


def read_pedestrian_references(path: Path) -> list[dict]:
    collection = json.loads(path.read_text(encoding="utf-8-sig"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Pedestrian references must be a GeoJSON FeatureCollection")
    crs = collection.get("crs", {}).get("properties", {}).get("name")
    if crs not in (None, "EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84"):
        raise ValueError("Pedestrian reference input must use WGS84 longitude/latitude")
    features = collection.get("features", [])
    if not features:
        raise ValueError("No pedestrian references supplied")
    ids = set()
    for feature in features:
        identity = feature.get("id")
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [])
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError("Each reference must have a unique nonempty string ID")
        ids.add(identity)
        if properties.get("kind") not in ("bridge", "intersection"):
            raise ValueError(f"Unsupported reference kind: {identity}")
        if geometry.get("type") != "Point" or len(coords) != 2:
            raise ValueError(f"Expected a WGS84 point: {identity}")
        if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and isfinite(n) for n in coords):
            raise ValueError(f"Invalid coordinates: {identity}")
        if not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
            raise ValueError(f"Coordinates outside WGS84 bounds: {identity}")
        if not all(properties.get(key) for key in ("source", "source_id", "position_semantics", "validation_status")):
            raise ValueError(f"Missing provenance or validation status: {identity}")
    return features
