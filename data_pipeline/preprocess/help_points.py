import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


class HelpPointValidationError(RuntimeError):
    """Raised when the AI-ready help point document itself is malformed."""


def _identifier(feature: dict[str, Any], properties: dict[str, Any]) -> str:
    for value in (
        feature.get("id"),
        properties.get("external_id"),
        properties.get("id"),
        properties.get("name"),
    ):
        if value not in (None, ""):
            return str(value)
    canonical = json.dumps(feature, ensure_ascii=False, sort_keys=True)
    return f"generated-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def validate_help_points(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HelpPointValidationError(f"Cannot read help point GeoJSON: {path}") from exc
    if document.get("type") != "FeatureCollection":
        raise HelpPointValidationError("Help points must be a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise HelpPointValidationError("Help point GeoJSON requires a features array")

    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    warnings: list[str] = []
    category_counts: Counter[str] = Counter()
    for feature in features:
        if not isinstance(feature, dict):
            excluded.append({"identifier": "(unknown)", "reason": "invalid_feature"})
            continue
        properties = feature.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        identifier = _identifier(feature, properties)
        geometry = feature.get("geometry")
        if geometry is None:
            excluded.append({"identifier": identifier, "reason": "geometry_null"})
            continue
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            excluded.append({"identifier": identifier, "reason": "not_point"})
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            excluded.append({"identifier": identifier, "reason": "coordinates_null"})
            continue
        if coordinates[0] in (None, ""):
            excluded.append({"identifier": identifier, "reason": "longitude_null"})
            continue
        if coordinates[1] in (None, ""):
            excluded.append({"identifier": identifier, "reason": "latitude_null"})
            continue
        longitude = _number(coordinates[0])
        latitude = _number(coordinates[1])
        if longitude is None or not -180 <= longitude <= 180:
            excluded.append({"identifier": identifier, "reason": "invalid_longitude"})
            continue
        if latitude is None or not -90 <= latitude <= 90:
            excluded.append({"identifier": identifier, "reason": "invalid_latitude"})
            continue

        property_longitude = _number(properties.get("longitude"))
        property_latitude = _number(properties.get("latitude"))
        if property_longitude is not None and abs(property_longitude - longitude) > 1e-7:
            warnings.append(f"{identifier}: geometry longitude overrides properties.longitude")
        if property_latitude is not None and abs(property_latitude - latitude) > 1e-7:
            warnings.append(f"{identifier}: geometry latitude overrides properties.latitude")

        category = properties.get("category")
        category_text = str(category).strip() if category not in (None, "") else None
        category_counts[category_text or "(NULL)"] += 1
        valid.append(
            {
                "external_id": identifier,
                "name": properties.get("name"),
                "category": category_text,
                "subtype": properties.get("subtype"),
                "address": properties.get("address"),
                "phone": properties.get("phone"),
                "emergency_phone": properties.get("emergency_phone"),
                "coordinate_quality": properties.get("coordinate_quality"),
                "coordinate_status": properties.get("coordinate_status"),
                "coordinate_source": properties.get("coordinate_source"),
                "source_org": properties.get("source_org"),
                "source_dataset": properties.get("source_dataset"),
                "reference_date": properties.get("reference_date"),
                "longitude": longitude,
                "latitude": latitude,
                "properties": properties,
            }
        )

    exclusion_counts = Counter(item["reason"] for item in excluded)
    return valid, {
        "total_feature_count": len(features),
        "valid_feature_count": len(valid),
        "excluded_feature_count": len(excluded),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "excluded_features": excluded,
        "category_counts": dict(sorted(category_counts.items())),
        "warnings": warnings,
        "source_file": path.name,
    }
