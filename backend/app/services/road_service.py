from app.repositories.road_repository import BoundingBox, list_road_segments, list_crossing_markers, list_osm_display_roads


def get_osm_display_collection(bbox_value: str | None):
    roads = list_osm_display_roads(parse_bbox(bbox_value))
    return {
        "type": "FeatureCollection",
        "features": [{"type":"Feature","id":r["id"],"geometry":r["geometry"],
                      "properties":{"highway":r["highway"],"name":r["name"]}} for r in roads],
        "metadata":{"count":len(roads),"crs":"EPSG:4326","source":"osm","display_only":True},
    }


def get_crossing_feature_collection(bbox_value: str | None = None) -> dict[str, object]:
    markers = list_crossing_markers(parse_bbox(bbox_value))
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": row["id"], "geometry": row["geometry"],
             "properties": {"source": "osm", "basis": row["basis"]}}
            for row in markers
        ],
        "metadata": {"count": len(markers), "crs": "EPSG:4326", "source": "osm"},
    }


class InvalidBoundingBoxError(ValueError):
    """Raised when an API bounding box is malformed."""


def parse_bbox(value: str | None) -> BoundingBox | None:
    if value is None:
        return None

    try:
        coordinates = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise InvalidBoundingBoxError("bbox must contain four numbers") from exc

    if len(coordinates) != 4:
        raise InvalidBoundingBoxError(
            "bbox must be minLongitude,minLatitude,maxLongitude,maxLatitude"
        )

    min_longitude, min_latitude, max_longitude, max_latitude = coordinates
    if not (-180 <= min_longitude < max_longitude <= 180):
        raise InvalidBoundingBoxError("bbox longitude range is invalid")
    if not (-90 <= min_latitude < max_latitude <= 90):
        raise InvalidBoundingBoxError("bbox latitude range is invalid")

    return BoundingBox(
        min_longitude=min_longitude,
        min_latitude=min_latitude,
        max_longitude=max_longitude,
        max_latitude=max_latitude,
    )


def get_road_feature_collection(
    bbox_value: str | None,
    source: str | None = None,
    steps_only: bool = False,
) -> dict[str, object]:
    roads = list_road_segments(parse_bbox(bbox_value), source=source, steps_only=steps_only)
    features = [
        {
            "type": "Feature",
            "id": road["id"],
            "geometry": road["geometry"],
            "properties": {
                key: value
                for key, value in road.items()
                if key not in {"id", "geometry"}
            },
        }
        for road in roads
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
