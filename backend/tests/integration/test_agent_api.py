from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import app
from app.schemas.agent import ParsedRouteIntent
from tests.integration.conftest import TEST_USER_ID


client = TestClient(app)


def test_selection_saves_crossing_preference_without_server_error():
    from uuid import uuid4
    from app.db.connection import connect_database
    from app.repositories.personalization_repository import save_recommendation

    user = f"test-intersection-{uuid4()}"
    try:
        recommendation = save_recommendation(user, [
            {"route_type": name, "metrics": {"crosswalk_count": exposure}}
            for name, exposure in [("shortest", 2), ("custom", 0)]
        ])
        response = client.post("/api/agent/route-selections", json={
            "recommendation_id": recommendation, "user_id": user,
            "selected_route_type": "custom",
        })
        assert response.status_code == 200
        learned = {p["factor"]: p for p in response.json()["preferences"]}
        assert learned["crosswalk_count"]["observations"] == 1
        assert learned["crosswalk_count"]["weight"] > 0.5
    finally:
        with connect_database() as connection:
            connection.execute("DELETE FROM route_selection_events WHERE user_id = %s", (user,))
            connection.execute("DELETE FROM route_recommendations WHERE user_id = %s", (user,))
            connection.execute("DELETE FROM user_route_preferences WHERE user_id = %s", (user,))


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
    assert payload["selected_route_type"] == "custom"
    assert len(payload["candidates"]) == 2
    assert payload["unsupported_preferences"] == []


def test_agent_propagates_stairs_weight_to_generated_routes() -> None:
    response = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "source": "test-fixture",
                "stairs_weight": 1.0,
                "preferences": [
                    {"factor": "distance_m", "direction": "minimize", "weight": 1}
                ],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert all(
        candidate["route"]["properties"]["cost_weights"]["stairs"] == (1.0 if candidate["route_type"] == "custom" else 0.0)
        for candidate in payload["candidates"]
    )
    shortest = next(
        candidate for candidate in payload["candidates"]
        if candidate["route_type"] == "shortest"
    )
    assert shortest["route"]["properties"]["stairs_segment_count"] == 2
    custom = next(c for c in payload["candidates"] if c["route_type"] == "custom")
    assert custom["route"]["properties"]["stairs_segment_count"] == 0


def test_agent_validates_stairs_weight_range() -> None:
    response = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "stairs_weight": 1.01,
            },
        },
    )

    assert response.status_code == 422


def test_agent_reports_registered_metrics_that_have_no_source_data() -> None:
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
                        "factor": "max_slope_percent",
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
    assert payload["unsupported_preferences"][0]["factor"] == "max_slope_percent"


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
    assert payload["result"]["selected_route_type"] == "custom"


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


def test_natural_language_query_resolves_place_names(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_api,
        "parse_route_intent",
        lambda _: ParsedRouteIntent.model_validate(
            {
                "origin_name": "주안역",
                "destination_name": "인천사랑병원",
                "departure_time": "22:00:00",
                "profile": "pedestrian",
                "preferences": [
                    {"factor": "cctv_score", "direction": "maximize", "weight": 1}
                ],
            }
        ),
    )

    places = {
        "주안역": {
            "name": "주안역",
            "category": "subway_station",
            "address": None,
            "source": "test",
            "latitude": 37.4608,
            "longitude": 126.6790,
        },
        "인천사랑병원": {
            "name": "인천사랑병원",
            "category": "hospital",
            "address": None,
            "source": "test",
            "latitude": 37.4608,
            "longitude": 126.6830,
        },
    }
    monkeypatch.setattr(agent_api, "resolve_place", lambda name: places[name])

    response = client.post(
        "/api/agent/query",
        json={
            "query": "밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘",
            "source": "test-fixture",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_origin"]["name"] == "주안역"
    assert payload["resolved_destination"]["name"] == "인천사랑병원"
    assert len(payload["result"]["candidates"]) == 2


def test_route_selection_updates_server_side_preferences() -> None:
    recommendation = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "source": "test-fixture",
                "user_id": TEST_USER_ID,
                "departure_time": "22:00:00",
            },
        },
    )

    assert recommendation.status_code == 200
    payload = recommendation.json()
    assert payload["recommendation_id"] is not None
    assert len(payload["candidates"]) == 2

    selection = client.post(
        "/api/agent/route-selections",
        json={
            "recommendation_id": payload["recommendation_id"],
            "user_id": TEST_USER_ID,
            "selected_route_type": "custom",
        },
    )

    assert selection.status_code == 200
    learned = selection.json()["preferences"]
    assert {item["factor"] for item in learned} == {
        "distance_m",
        "safety_score",
        "streetlight_score",
        "cctv_score",
        "crosswalk_count",
        "stairs_distance_m",
        "sidewalk_coverage_percent",
    }
    assert all(item["observations"] == 1 for item in learned)

    # Map and result-card clicks can change the choice for the same recommendation.
    # The existing unique recommendation record must be updated, not rejected.
    for route_type in ["shortest", "custom"]:
        changed = client.post("/api/agent/route-selections", json={
            "recommendation_id": payload["recommendation_id"],
            "user_id": TEST_USER_ID,
            "selected_route_type": route_type,
        })
        assert changed.status_code == 200, changed.text
        assert changed.json()["selected_route_type"] == route_type


def test_route_selection_rejects_another_user() -> None:
    recommendation = client.post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.4608, "longitude": 126.6790},
                "destination": {"latitude": 37.4608, "longitude": 126.6830},
                "source": "test-fixture",
                "user_id": TEST_USER_ID,
            },
        },
    ).json()

    response = client.post(
        "/api/agent/route-selections",
        json={
            "recommendation_id": recommendation["recommendation_id"],
            "user_id": "another-user",
            "selected_route_type": "custom",
        },
    )

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]
