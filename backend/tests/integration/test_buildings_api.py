from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
TEST_BUILDING_SOURCE = "test-building-fixture"


def test_buildings_are_returned_as_wgs84_geojson() -> None:
    response = client.get(
        "/api/buildings",
        params={"source": TEST_BUILDING_SOURCE},
    )

    assert response.status_code == 200
    collection = response.json()
    assert collection["type"] == "FeatureCollection"
    assert collection["metadata"] == {
        "count": 2,
        "crs": "EPSG:4326",
        "source": TEST_BUILDING_SOURCE,
    }
    assert all(
        feature["geometry"]["type"] == "MultiPolygon"
        for feature in collection["features"]
    )
    longitude = collection["features"][0]["geometry"]["coordinates"][0][0][0][0]
    latitude = collection["features"][0]["geometry"]["coordinates"][0][0][0][1]
    assert 126.67 < longitude < 126.69
    assert 37.45 < latitude < 37.47


def test_building_bbox_filters_in_postgis() -> None:
    response = client.get(
        "/api/buildings",
        params={
            "source": TEST_BUILDING_SOURCE,
            "bbox": "126.6799,37.4609,126.6803,37.4613",
        },
    )

    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["count"] == 1
    assert collection["features"][0]["properties"]["building_id"] == "building-001"


def test_invalid_building_bbox_is_rejected() -> None:
    response = client.get(
        "/api/buildings",
        params={"source": TEST_BUILDING_SOURCE, "bbox": "126,37,125,38"},
    )

    assert response.status_code == 400
