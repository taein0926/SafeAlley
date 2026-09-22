from app.repositories.place_repository import (
    PlaceNotFoundError,
    PlaceRepositoryError,
    cache_geocoded_place,
    find_place,
    get_osm_road_viewbox,
)
from app.services.geocoding_service import (
    GeocodingServiceError,
    geocode_place,
    reverse_geocode_place,
)


def resolve_place(name: str) -> dict[str, object]:
    """Resolve through PostGIS first, then one bounded and cached OSM fallback."""

    local_place = find_place(name)
    if local_place is not None:
        return local_place

    try:
        geocoded_place = geocode_place(name, get_osm_road_viewbox())
    except GeocodingServiceError as exc:
        raise PlaceRepositoryError(
            "외부 장소 검색 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from exc
    if geocoded_place is None:
        raise PlaceNotFoundError(
            f"'{name}' 장소를 미추홀구 도로 범위에서 찾지 못했습니다."
        )

    cache_geocoded_place(geocoded_place, name)
    return {
        key: geocoded_place[key]
        for key in (
            "name",
            "category",
            "address",
            "source",
            "latitude",
            "longitude",
        )
    }


def reverse_place(latitude: float, longitude: float) -> dict[str, object]:
    """Resolve and cache a map-selected coordinate inside the routing area."""

    bounds = get_osm_road_viewbox()
    min_lon, min_lat, max_lon, max_lat = bounds
    if not (min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat):
        raise PlaceNotFoundError("선택한 위치가 미추홀구 도로 범위 밖에 있습니다.")
    try:
        place = reverse_geocode_place(latitude, longitude)
    except GeocodingServiceError as exc:
        raise PlaceRepositoryError(
            "외부 주소 검색 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from exc

    cache_geocoded_place(place, str(place["name"]))
    return {
        key: place[key]
        for key in (
            "name",
            "category",
            "address",
            "source",
            "latitude",
            "longitude",
        )
    }
