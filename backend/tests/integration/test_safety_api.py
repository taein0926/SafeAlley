from fastapi.testclient import TestClient

from app.main import app
client = TestClient(app)
TEST_SOURCE = "test-fixture"
TEST_STREETLIGHT_SOURCE = "test-streetlight-fixture"
TEST_CCTV_SOURCE = "test-cctv-fixture"
TEST_HELP_POINT_SOURCE = "test-help-point-fixture"


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
    assert feature["properties"]["streetlight_score"] == 82.0
    assert feature["properties"]["cctv_score"] == 68.0
    assert feature["properties"]["help_point_score"] == 74.0
    assert feature["properties"]["highway"] == "steps"
    assert feature["properties"]["is_steps"] is True
    assert feature["properties"]["incline"] == "up"


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


def test_cctv_api_returns_only_safety_points_in_epsg4326() -> None:
    response = client.get("/api/cctvs", params={"source": TEST_CCTV_SOURCE})
    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["count"] == 1
    assert collection["metadata"]["crs"] == "EPSG:4326"
    feature = collection["features"][0]
    assert feature["properties"]["purpose"] == "방범"
    longitude, latitude = feature["geometry"]["coordinates"]
    assert abs(longitude - 126.6801) < 0.00001
    assert abs(latitude - 37.4611) < 0.00001


def test_help_point_api_supports_category_filter() -> None:
    response = client.get(
        "/api/help-points",
        params={"source": TEST_HELP_POINT_SOURCE, "category": "police"},
    )
    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["count"] == 1
    assert collection["metadata"]["crs"] == "EPSG:4326"
    assert collection["features"][0]["properties"]["category"] == "police"

    excluded = client.get(
        "/api/help-points",
        params={"source": TEST_HELP_POINT_SOURCE, "category": "fire_station"},
    )
    assert excluded.status_code == 200
    assert excluded.json()["metadata"]["count"] == 0
