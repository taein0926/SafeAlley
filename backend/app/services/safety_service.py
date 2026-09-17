from app.repositories.safety_repository import (
    list_cctvs,
    list_help_points,
    list_safety_segments,
    list_streetlights,
)
from app.services.road_service import parse_bbox


def _feature_collection(
    rows: list[dict[str, object]],
    *,
    source: str | None,
) -> dict[str, object]:
    features = [
        {
            "type": "Feature",
            "id": row["id"],
            "geometry": row["geometry"],
            "properties": {
                key: value
                for key, value in row.items()
                if key not in {"id", "geometry"}
            },
        }
        for row in rows
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count": len(features),
            "crs": "EPSG:4326",
            "source": source,
        },
    }


def get_safety_road_feature_collection(
    bbox_value: str | None,
    source: str | None,
) -> dict[str, object]:
    return _feature_collection(
        list_safety_segments(parse_bbox(bbox_value), source=source),
        source=source,
    )


def get_streetlight_feature_collection(
    bbox_value: str | None,
    source: str | None,
) -> dict[str, object]:
    return _feature_collection(
        list_streetlights(parse_bbox(bbox_value), source=source),
        source=source,
    )


def get_cctv_feature_collection(
    bbox_value: str | None,
    source: str | None,
    *,
    safety_only: bool,
) -> dict[str, object]:
    return _feature_collection(
        list_cctvs(parse_bbox(bbox_value), source=source, safety_only=safety_only),
        source=source,
    )


def get_help_point_feature_collection(
    bbox_value: str | None,
    source: str | None,
    category: str | None,
) -> dict[str, object]:
    return _feature_collection(
        list_help_points(
            parse_bbox(bbox_value), source=source, category=category
        ),
        source=source,
    )
