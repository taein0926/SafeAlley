import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
START = {"latitude": 37.4608, "longitude": 126.6790}
END = {"latitude": 37.4608, "longitude": 126.6830}


@pytest.mark.parametrize("route_type", ["shortest", "balanced", "safe"])
@pytest.mark.parametrize("departure,included", [("14:00:00", False), ("22:00:00", True)])
def test_route_endpoints_apply_daylight_policy(route_type, departure, included):
    response = client.post(f"/api/routes/{route_type}", json={
        "start": START, "end": END, "source": "test-fixture",
        "departure_time": departure, "stairs_weight": 1,
    })
    assert response.status_code == 200, response.text
    properties = response.json()["properties"]
    assert properties["streetlight_included"] is included
    assert properties["cost_weights"]["stairs"] == 1
    for segment in properties["road_segments"]:
        assert "highway" in segment and "is_steps" in segment
        if not included:
            expected = (segment["cctv_score"] * 0.4 + segment["help_point_score"] * 0.2) / 0.6
            assert segment["safety_score"] == pytest.approx(expected, abs=0.01)


def test_agent_daylight_metrics_and_ranking_ignore_lighting():
    response = client.post("/api/agent/execute", json={
        "tool": "rank_routes",
        "arguments": {
            "origin": START, "destination": END, "source": "test-fixture",
            "departure_time": "14:00:00", "preferences": [
                {"factor": "streetlight_score", "direction": "maximize", "weight": 100},
                {"factor": "safety_score", "direction": "maximize", "weight": 1},
            ],
        },
    })
    assert response.status_code == 200, response.text
    data = response.json()
    for candidate in data["candidates"]:
        assert candidate["route"]["properties"]["streetlight_included"] is False
        assert candidate["metrics"]["streetlight_score"] is None
        assert candidate["metrics"]["safety_score"] == candidate["route"]["properties"]["average_safety_score"]
    assert data["selected_route_type"] is not None
    assert data["unsupported_preferences"] == [{"factor": "streetlight_score", "reason": "Excluded during daylight"}]
    assert "가로등" not in data["recommendation_reason"]
