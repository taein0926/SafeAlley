from app.repositories.road_repository import BoundingBox, list_road_segments


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
) -> dict[str, object]:
    roads = list_road_segments(parse_bbox(bbox_value), source=source)
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
