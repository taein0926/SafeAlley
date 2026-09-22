from fastapi.testclient import TestClient

from app.main import app
from app.repositories.pedestrian_reference_repository import PedestrianReferenceError
from app.services import pedestrian_reference_service

client = TestClient(app)


def test_bridge_geojson_preserves_unconnected_references_and_provenance(monkeypatch):
    rows = [
        {"id": "bridge-a", "geometry": {"type": "Point", "coordinates": [126.68, 37.46]},
         "properties": {"name": "연결 육교", "address": "테스트 주소", "validation_status": "unverified"},
         "routing_connected": True},
        {"id": "bridge-b", "geometry": {"type": "Point", "coordinates": [126.69, 37.45]},
         "properties": {"name": "미연결 육교", "routing_connected": True}, "routing_connected": False},
    ]
    monkeypatch.setattr(pedestrian_reference_service, "list_pedestrian_bridges", lambda: rows)
    response = client.get("/api/pedestrian-bridges")
    assert response.status_code == 200
    result = response.json()
    assert result["metadata"] == {"count": 2, "crs": "EPSG:4326", "routing_connected_count": 1}
    assert result["features"][0]["properties"]["validation_status"] == "unverified"
    assert result["features"][0]["properties"]["address"] == "테스트 주소"
    assert result["features"][1]["properties"]["routing_connected"] is False
    assert result["features"][1]["geometry"] == rows[1]["geometry"]


def test_empty_bridge_dataset_is_valid(monkeypatch):
    monkeypatch.setattr(pedestrian_reference_service, "list_pedestrian_bridges", lambda: [])
    response = client.get("/api/pedestrian-bridges")
    assert response.status_code == 200
    assert response.json()["features"] == []
    assert response.json()["metadata"]["count"] == 0


def test_unavailable_bridge_data_returns_503_not_fake_empty_success(monkeypatch):
    def fail():
        raise PedestrianReferenceError("internal connection details")
    monkeypatch.setattr(pedestrian_reference_service, "list_pedestrian_bridges", fail)
    response = client.get("/api/pedestrian-bridges")
    assert response.status_code == 503
    assert "internal connection details" not in response.text
