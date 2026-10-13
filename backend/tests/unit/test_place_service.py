import pytest

from app.repositories.place_repository import PlaceNotFoundError, PlaceAmbiguousError, PlaceRepositoryError
from app.repositories.building_repository import BuildingPlaceAmbiguousError, BuildingRepositoryError
from app.services import place_service


LOCAL_PLACE = {
    "name": "주안역",
    "category": "subway_station",
    "address": "인천광역시 미추홀구",
    "source": "demo",
    "latitude": 37.4649,
    "longitude": 126.6804,
}


@pytest.fixture(autouse=True)
def no_gis_match_by_default(monkeypatch):
    monkeypatch.setattr(place_service, "find_building_place", lambda *_: None)


def test_local_place_is_returned_without_fallback(monkeypatch) -> None:
    monkeypatch.setattr(place_service, "find_place", lambda _: LOCAL_PLACE)
    monkeypatch.setattr(place_service, "find_building_place", lambda *_: pytest.fail("places wins"))
    monkeypatch.setattr(
        place_service,
        "geocode_place",
        lambda *_: pytest.fail("fallback must not be called for a local hit"),
    )

    assert place_service.resolve_place("주안역") == LOCAL_PLACE


def test_gis_building_precedes_nominatim_without_copying_into_places(monkeypatch):
    bounds = (126.6, 37.4, 126.75, 37.52)
    building = {**LOCAL_PLACE, "name": "두리하나어린이집 및 육아종합지원센터", "source": "molit-gis-building"}
    calls = []
    monkeypatch.setattr(place_service, "find_place", lambda _: None)
    monkeypatch.setattr(place_service, "get_osm_road_viewbox", lambda: bounds)
    monkeypatch.setattr(place_service, "find_building_place", lambda *args: calls.append(args) or building)
    monkeypatch.setattr(place_service, "geocode_place", lambda *_: pytest.fail("GIS match must not call Nominatim"))
    monkeypatch.setattr(place_service, "cache_geocoded_place", lambda *_: pytest.fail("GIS must stay in its source table"))
    assert place_service.resolve_place(" 두리하나어린이집 ") == building
    assert calls == [("두리하나어린이집", bounds)]


@pytest.mark.parametrize("error,expected", [
    (BuildingPlaceAmbiguousError("전체 주소로 검색해주세요"), PlaceAmbiguousError),
    (BuildingRepositoryError("unavailable"), PlaceRepositoryError),
])
def test_gis_failure_is_not_silently_replaced_by_nominatim(monkeypatch, error, expected):
    monkeypatch.setattr(place_service, "find_place", lambda _: None)
    monkeypatch.setattr(place_service, "get_osm_road_viewbox", lambda: (126.6,37.4,126.75,37.52))
    def fail(*_):
        raise error
    monkeypatch.setattr(place_service, "find_building_place", fail)
    monkeypatch.setattr(place_service, "geocode_place", lambda *_: pytest.fail("must not replace ambiguous/failed GIS lookup"))
    with pytest.raises(expected):
        place_service.resolve_place("동일건물")


def test_building_selection_context_is_preserved(monkeypatch):
    context = {
        "code": "building_selection_required",
        "place_name": "테스트아파트",
        "focus": {"west": 126.65, "south": 37.45, "east": 126.66, "north": 37.46},
    }
    monkeypatch.setattr(place_service, "find_place", lambda _: None)
    monkeypatch.setattr(place_service, "get_osm_road_viewbox", lambda: (126.6, 37.4, 126.75, 37.52))
    def ambiguous(*_):
        raise BuildingPlaceAmbiguousError("동을 선택해 주세요.", selection_context=context)
    monkeypatch.setattr(place_service, "find_building_place", ambiguous)
    with pytest.raises(PlaceAmbiguousError) as raised:
        place_service.resolve_place("테스트아파트")
    assert raised.value.api_detail(target="origin") == {
        "message": "동을 선택해 주세요.", "target": "origin", **context,
    }


def test_blank_name_does_not_search_any_database(monkeypatch):
    monkeypatch.setattr(place_service, "find_place", lambda *_: pytest.fail("empty search"))
    with pytest.raises(PlaceNotFoundError):
        place_service.resolve_place("   ")


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
