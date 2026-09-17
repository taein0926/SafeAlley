from app.repositories.building_repository import (
    BuildingBoundingBox,
    list_buildings,
)


class InvalidBuildingBoundingBoxError(ValueError):
    """Raised when a building API bounding box is malformed."""


def parse_building_bbox(value: str | None) -> BuildingBoundingBox | None:
    if value is None:
        return None

    try:
        coordinates = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise InvalidBuildingBoundingBoxError(
            "bbox must contain four numbers"
        ) from exc

    if len(coordinates) != 4:
        raise InvalidBuildingBoundingBoxError(
            "bbox must be minLongitude,minLatitude,maxLongitude,maxLatitude"
        )

    min_longitude, min_latitude, max_longitude, max_latitude = coordinates
    if not (-180 <= min_longitude < max_longitude <= 180):
        raise InvalidBuildingBoundingBoxError("bbox longitude range is invalid")
    if not (-90 <= min_latitude < max_latitude <= 90):
        raise InvalidBuildingBoundingBoxError("bbox latitude range is invalid")

    return BuildingBoundingBox(
        min_longitude=min_longitude,
        min_latitude=min_latitude,
        max_longitude=max_longitude,
        max_latitude=max_latitude,
    )


def get_building_feature_collection(
    bbox_value: str | None,
    source: str | None = None,
) -> dict[str, object]:
    buildings = list_buildings(parse_building_bbox(bbox_value), source=source)
    features = [
        {
            "type": "Feature",
            "id": building["id"],
            "geometry": building["geometry"],
            "properties": {
                key: value
                for key, value in building.items()
                if key not in {"id", "geometry"}
            },
        }
        for building in buildings
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

