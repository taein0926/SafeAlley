from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_roads_can_be_filtered_to_test_fixture() -> None:
    response = client.get("/api/roads", params={"source": "test-fixture"})

    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["source"] == "test-fixture"
    assert collection["metadata"]["count"] == 4
    assert all(
        feature["properties"]["source"] == "test-fixture"
        for feature in collection["features"]
    )
    assert collection["features"][0]["properties"]["highway"] == "steps"
    assert collection["features"][0]["properties"]["is_steps"] is True
    assert collection["features"][0]["properties"]["incline"] == "up"
    assert collection["features"][2]["properties"]["highway"] == "footway"
    assert collection["features"][2]["properties"]["is_steps"] is False


def test_roads_can_filter_stairs_without_other_roads() -> None:
    response = client.get(
        "/api/roads", params={"source": "test-fixture", "steps_only": True}
    )
    assert response.status_code == 200
    collection = response.json()
    assert collection["metadata"]["count"] == 2
    assert all(
        feature["properties"]["is_steps"] is True
        and feature["properties"]["source"] == "test-fixture"
        for feature in collection["features"]
    )


def test_stairs_filter_respects_bbox() -> None:
    response = client.get(
        "/api/roads",
        params={
            "source": "test-fixture",
            "steps_only": True,
            "bbox": "126.6792,37.4607,126.6798,37.4609",
        },
    )
    assert response.status_code == 200
    assert response.json()["metadata"]["count"] == 1


def test_stairs_filter_rejects_invalid_value() -> None:
    response = client.get("/api/roads", params={"steps_only": "invalid"})
    assert response.status_code == 422
