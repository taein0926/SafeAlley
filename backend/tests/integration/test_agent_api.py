from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_agent_ranks_routes_from_structured_output() -> None:
    response = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "departure_time": "22:00:00",
                "profile": "pedestrian",
                "source": "test-fixture",
                "preferences": [
                    {
                        "factor": "safety_score",
                        "direction": "maximize",
                        "weight": 1,
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_route_type"] == "safe"
    assert len(payload["candidates"]) == 2
    assert payload["unsupported_preferences"] == []


def test_agent_reports_metrics_that_have_no_registered_data() -> None:
    response = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "source": "test-fixture",
                "preferences": [
                    {
                        "factor": "crosswalk_count",
                        "direction": "minimize",
                        "weight": 1,
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_route"] is None
    assert payload["unsupported_preferences"][0]["factor"] == "crosswalk_count"


def test_agent_rejects_unregistered_tools_and_extra_fields() -> None:
    response = client.post(
        "/api/agent/execute",
        json={
            "tool": "execute_sql",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "sql": "SELECT 1",
            },
        },
    )

    assert response.status_code == 422
