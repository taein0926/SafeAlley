import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import connect_database
from app.main import app

client = TestClient(app)
REQUEST = {
    "start": {"longitude": 126.679, "latitude": 37.4608},
    "end": {"longitude": 126.681, "latitude": 37.4608},
    "source": "test-fixture",
}


@pytest.fixture
def annotated_test_edge():
    with connect_database() as connection:
        row = connection.execute("SELECT id, properties FROM road_segments WHERE source='test-fixture' AND source_id='test-road-001'").fetchone()
        props = {**row[1], "pedestrian_reference": {
            "version": "pedestrian-reference-v1", "intersection_exposure_m": 30,
            "grade_separated": False, "bridge_ids": [],
        }}
        connection.execute("UPDATE road_segments SET properties=%s WHERE id=%s", (Jsonb(props), row[0]))
    try:
        yield
    finally:
        with connect_database() as connection:
            connection.execute("UPDATE road_segments SET properties=%s WHERE id=%s", (Jsonb(row[1]), row[0]))


def test_intersection_schema_cost_and_reverse_metadata(annotated_test_edge):
    default = client.post("/api/routes/shortest", json=REQUEST).json()
    zero = client.post("/api/routes/shortest", json={**REQUEST, "intersection_weight": 0}).json()
    assert default == zero
    for start, end in ((REQUEST["start"], REQUEST["end"]), (REQUEST["end"], REQUEST["start"])):
        response = client.post("/api/routes/shortest", json={**REQUEST, "start": start, "end": end, "intersection_weight": 1})
        assert response.status_code == 200
        p = response.json()["properties"]
        assert p["intersection_data_available"] is True
        assert p["intersection_distance_m"] == 30
        assert p["cost_weights"]["intersection"] == 1
        assert p["stairs_segment_count"] == 1
        assert p["road_segments"][0]["intersection_penalty"] == 120
        assert p["total_distance_m"] <= p["intersection_distance_limit_m"]
        assert p["total_cost"] == pytest.approx(default["properties"]["total_cost"] + 120, abs=0.01)


def test_agent_propagates_intersection_and_stair_weights(annotated_test_edge):
    response = client.post("/api/agent/execute", json={"tool": "rank_routes", "arguments": {
        "origin": REQUEST["start"], "destination": REQUEST["end"], "source": "test-fixture",
        "intersection_weight": 0.7, "stairs_weight": 0.4,
        "preferences": [{"factor": "intersection_distance_m", "direction": "minimize", "weight": 70}],
    }})
    assert response.status_code == 200
    result = response.json()
    assert result["unsupported_preferences"] == []
    for candidate in result["candidates"]:
        p = candidate["route"]["properties"]
        assert p["cost_weights"]["intersection"] == 0.7
        assert p["cost_weights"]["stairs"] == 0.4
        assert p["total_distance_m"] <= p["intersection_distance_limit_m"] + 0.01


@pytest.mark.parametrize("weight", [-0.01, 1.01])
def test_api_rejects_invalid_intersection_weight(weight):
    assert client.post("/api/routes/shortest", json={**REQUEST, "intersection_weight": weight}).status_code == 422
    assert client.post("/api/agent/execute", json={"tool": "rank_routes", "arguments": {
        "origin": REQUEST["start"], "destination": REQUEST["end"], "intersection_weight": weight,
    }}).status_code == 422


def test_unlinked_data_does_not_claim_to_be_complete():
    response = client.post("/api/routes/shortest", json={**REQUEST, "intersection_weight": 1})
    assert response.status_code == 200
    assert response.json()["properties"]["intersection_data_available"] is False
