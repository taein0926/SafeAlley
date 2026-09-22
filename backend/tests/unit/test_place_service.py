import pytest

from app.repositories.place_repository import PlaceNotFoundError
from app.services import place_service


LOCAL_PLACE = {
    "name": "주안역",
    "category": "subway_station",
    "address": "인천광역시 미추홀구",
    "source": "demo",
    "latitude": 37.4649,
    "longitude": 126.6804,
}


def test_local_place_is_returned_without_fallback(monkeypatch) -> None:
    monkeypatch.setattr(place_service, "find_place", lambda _: LOCAL_PLACE)
    monkeypatch.setattr(
        place_service,
        "geocode_place",
        lambda *_: pytest.fail("fallback must not be called for a local hit"),
    )

    assert place_service.resolve_place("주안역") == LOCAL_PLACE


def test_fallback_result_is_cached(monkeypatch) -> None:
    bounds = (126.6, 37.4, 126.75, 37.52)
    geocoded = {
        "name": "인하대학교",
        "category": "university",
        "address": "인하대학교, 미추홀구, 인천광역시",
        "source": "nominatim-osm",
        "source_id": "way-1",
        "latitude": 37.45,
        "longitude": 126.65,
    }
    cached: list[tuple[dict[str, object], str]] = []
    monkeypatch.setattr(place_service, "find_place", lambda _: None)
    monkeypatch.setattr(place_service, "get_osm_road_viewbox", lambda: bounds)
    monkeypatch.setattr(place_service, "geocode_place", lambda *_: geocoded)
    monkeypatch.setattr(
        place_service,
        "cache_geocoded_place",
        lambda place, query: cached.append((place, query)),
    )

    result = place_service.resolve_place("인하대학교")

    assert result["source"] == "nominatim-osm"
    assert cached == [(geocoded, "인하대학교")]


def test_missing_bounded_fallback_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(place_service, "find_place", lambda _: None)
    monkeypatch.setattr(
        place_service,
        "get_osm_road_viewbox",
        lambda: (126.6, 37.4, 126.75, 37.52),
    )
    monkeypatch.setattr(place_service, "geocode_place", lambda *_: None)

    with pytest.raises(PlaceNotFoundError, match="미추홀구 도로 범위"):
        place_service.resolve_place("없는 장소")


def test_reverse_place_rejects_coordinate_outside_routing_bounds(monkeypatch) -> None:
    monkeypatch.setattr(
        place_service,
        "get_osm_road_viewbox",
        lambda: (126.6, 37.4, 126.75, 37.52),
    )
    monkeypatch.setattr(
        place_service,
        "reverse_geocode_place",
        lambda *_: pytest.fail("out-of-bounds coordinates must not call Nominatim"),
    )

    with pytest.raises(PlaceNotFoundError, match="범위 밖"):
        place_service.reverse_place(37.8, 127.1)
