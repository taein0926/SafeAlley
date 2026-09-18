from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import app
from app.schemas.agent import ParsedRouteIntent


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


def test_natural_language_query_uses_local_interpretation(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_api,
        "parse_route_intent",
        lambda _: ParsedRouteIntent.model_validate(
            {
                "departure_time": "22:00:00",
                "profile": "pedestrian",
                "preferences": [
                    {
                        "factor": "streetlight_score",
                        "direction": "maximize",
                        "weight": 1,
                    }
                ],
            }
        ),
    )

    response = client.post(
        "/api/agent/query",
        json={
            "query": "밤 10시에 가로등이 많은 길로 안내해줘",
            "origin": {"latitude": 37.4608, "longitude": 126.6790},
            "destination": {"latitude": 37.4608, "longitude": 126.6830},
            "source": "test-fixture",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "qwen3:4b"
    assert payload["interpretation"]["departure_time"] == "22:00:00"
    assert payload["result"]["selected_route_type"] == "safe"


def test_natural_language_query_does_not_fallback_when_llm_fails(monkeypatch) -> None:
    from app.services.local_llm_service import LocalLLMOutputError

    def fail(_: str) -> ParsedRouteIntent:
        raise LocalLLMOutputError("invalid local model output")

    monkeypatch.setattr(agent_api, "parse_route_intent", fail)

    response = client.post(
        "/api/agent/query",
        json={
            "query": "가로등이 많은 길로 안내해줘",
            "origin": {"latitude": 37.4608, "longitude": 126.6790},
            "destination": {"latitude": 37.4608, "longitude": 126.6830},
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "invalid local model output"
