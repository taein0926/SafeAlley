from fastapi.testclient import TestClient

from app.api import places as places_api
from app.main import app
from app.repositories.place_repository import PlaceNotFoundError


client = TestClient(app)


def test_resolve_place_reuses_local_place_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        places_api,
        "resolve_place",
        lambda name: {
            "name": name,
            "category": "university",
            "address": "인천광역시 미추홀구",
            "source": "test",
            "latitude": 37.45,
            "longitude": 126.65,
        },
    )

    response = client.get("/api/places/resolve", params={"name": "인하대학교"})

    assert response.status_code == 200
    assert response.json()["name"] == "인하대학교"


def test_resolve_place_returns_not_found(monkeypatch) -> None:
    def not_found(_: str) -> dict[str, object]:
        raise PlaceNotFoundError("장소 없음")

    monkeypatch.setattr(places_api, "resolve_place", not_found)
    response = client.get("/api/places/resolve", params={"name": "없는 장소"})

    assert response.status_code == 404
    assert response.json()["detail"] == "장소 없음"


def test_reverse_place_returns_map_label(monkeypatch) -> None:
    monkeypatch.setattr(
        places_api,
        "reverse_place",
        lambda latitude, longitude: {
            "name": "인천대로",
            "category": "road",
            "address": "인천대로, 미추홀구, 인천광역시",
            "source": "nominatim-osm",
            "latitude": latitude,
            "longitude": longitude,
        },
    )

    response = client.get(
        "/api/places/reverse",
        params={"latitude": 37.45, "longitude": 126.65},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "인천대로"
