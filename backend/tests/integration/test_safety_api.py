from fastapi.testclient import TestClient

from app.main import app
client = TestClient(app)
TEST_SOURCE = "test-fixture"
TEST_STREETLIGHT_SOURCE = "test-streetlight-fixture"


def test_safety_road_api_returns_analysis_geojson() -> None:
    response = client.get("/api/safety/roads", params={"source": TEST_SOURCE})
    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"] == {
        "count": 4,
        "crs": "EPSG:4326",
        "source": TEST_SOURCE,
    }
    feature = collection["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert feature["properties"]["segment_id"] == feature["id"]
    assert feature["properties"]["nearest_light_distance_m"] == 4.5
    assert feature["properties"]["nearby_light_count"] == 2
    assert feature["properties"]["safety_score"] == 76.5


def test_streetlight_api_returns_epsg4326_points() -> None:
    response = client.get(
        "/api/streetlights", params={"source": TEST_STREETLIGHT_SOURCE}
    )
    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["count"] == 1
    assert collection["metadata"]["crs"] == "EPSG:4326"
    longitude, latitude = collection["features"][0]["geometry"]["coordinates"]
    assert abs(longitude - 126.68) < 0.00001
    assert abs(latitude - 37.461) < 0.00001
