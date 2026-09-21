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
