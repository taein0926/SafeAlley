from fastapi.testclient import TestClient

from app.main import app
from app.services import road_service
from app.api import roads
from app.repositories.road_repository import RoadRepositoryError


def test_crossing_collection_preserves_wgs84_geometry_and_basis(monkeypatch):
    monkeypatch.setattr(road_service, "list_crossing_markers", lambda bbox=None: [
        {"id": "group-12", "basis": "crossing_line",
         "geometry": {"type": "Point", "coordinates": [126.66, 37.46]}},
        {"id": "node-34", "basis": "crossing_node",
         "geometry": {"type": "Point", "coordinates": [126.67, 37.47]}},
    ])
    response = TestClient(app).get("/api/crossings")
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == {"count": 2, "crs": "EPSG:4326", "source": "osm"}
    assert data["features"][0]["geometry"]["coordinates"] == [126.66, 37.46]
    assert data["features"][1]["properties"]["basis"] == "crossing_node"


def test_empty_crossing_collection_is_valid(monkeypatch):
    monkeypatch.setattr(road_service, "list_crossing_markers", lambda bbox=None: [])
    assert road_service.get_crossing_feature_collection()["features"] == []


def test_crossing_bbox_is_validated_and_passed_to_repository(monkeypatch):
    seen = []
    monkeypatch.setattr(road_service, "list_crossing_markers", lambda bbox=None: seen.append(bbox) or [])
    client = TestClient(app)
    assert client.get("/api/crossings?bbox=126.66,37.46,126.67,37.47").status_code == 200
    assert seen[0].min_longitude == 126.66
    assert client.get("/api/crossings?bbox=invalid").status_code == 400
    assert len(seen) == 1


def test_crossing_repository_failure_returns_503_without_details(monkeypatch):
    def fail(bbox=None):
        raise RoadRepositoryError("private connection detail")
    monkeypatch.setattr(roads, "get_crossing_feature_collection", fail)
    response = TestClient(app).get("/api/crossings")
    assert response.status_code == 503
    assert "private" not in response.text
