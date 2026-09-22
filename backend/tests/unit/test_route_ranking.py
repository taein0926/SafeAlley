import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.agent import RouteOptimizationArguments, RoutePreference
from app.services import route_ranking_service


@pytest.fixture(autouse=True)
def balanced_route_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_balanced_route",
        lambda **_: _route("balanced", 115, 55),
    )


def _route(route_type: str, distance: float, score: float) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[126.6, 37.4], [126.7, 37.5]]},
        "properties": {
            "route_type": route_type,
            "crs": "EPSG:4326",
            "total_distance": distance,
            "total_distance_m": distance,
            "average_safety_score": score,
            "total_cost": distance,
            "cost_weights": {"distance": 1.0, "risk": 0.0},
            "start_node_id": 1,
            "end_node_id": 2,
            "start_snap_distance_m": 0.0,
            "end_snap_distance_m": 0.0,
            "road_segments": [
                {
                    "id": 1,
                    "source_id": route_type,
                    "name": None,
                    "from_node_id": 1,
                    "to_node_id": 2,
                    "distance_m": distance,
                    "streetlight_score": score,
                    "cctv_score": score,
                    "population_score": score,
                    "safety_score": score,
                    "coordinates": [[126.6, 37.4], [126.7, 37.5]],
                    "distance_factor": distance,
                    "risk_factor": 0.0,
                    "traversal_cost": distance,
                }
            ],
        },
    }


def _arguments(
    preferences: list[dict[str, object]],
    departure_time: str | None = None,
) -> RouteOptimizationArguments:
    return RouteOptimizationArguments.model_validate(
        {
            "origin": {"latitude": 37.46, "longitude": 126.67},
            "destination": {"latitude": 37.47, "longitude": 126.68},
            "preferences": preferences,
            "departure_time": departure_time,
        }
    )


def test_ranking_combines_registered_metrics(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_safe_route",
        lambda **_: _route("safe", 130, 90),
    )

    result = route_ranking_service.rank_route_candidates(
        _arguments(
            [
                {"factor": "distance_m", "direction": "minimize", "weight": 1},
                {"factor": "streetlight_score", "direction": "maximize", "weight": 3},
            ]
        )
    )

    assert result["selected_route_type"] == "safe"
    assert result["unsupported_preferences"] == []


def test_unknown_metrics_are_reported_without_substitution(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_safe_route",
        lambda **_: _route("safe", 130, 90),
    )

    result = route_ranking_service.rank_route_candidates(
        _arguments(
            [
                {"factor": "crosswalk_count", "direction": "minimize", "weight": 1},
                {"factor": "stairs", "direction": "avoid", "weight": 1},
            ]
        )
    )

    assert result["selected_route_type"] is None
    assert [item.factor for item in result["unsupported_preferences"]] == [
        "crosswalk_count",
        "stairs",
    ]
    assert all(candidate["preference_score"] is None for candidate in result["candidates"])


def test_registered_metric_without_candidate_data_is_not_scored() -> None:
    candidates = [
        {
            "route_type": "shortest",
            "preference_score": None,
            "metrics": {"streetlight_score": None},
            "route": _route("shortest", 100, 20),
        },
        {
            "route_type": "safe",
            "preference_score": None,
            "metrics": {"streetlight_score": 80.0},
            "route": _route("safe", 120, 80),
        },
    ]

    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates,
        [RoutePreference(factor="streetlight_score", direction="maximize")],
    )

    assert selected is None
    assert unsupported[0].factor == "streetlight_score"
    assert "data is unavailable" in unsupported[0].reason
    assert all(candidate["preference_score"] is None for candidate in candidates)


def test_avoid_stairs_is_a_hard_constraint() -> None:
    candidates = [
        {"route_type": "shortest", "preference_score": None,
         "metrics": {"distance_m": 100, "stairs_distance_m": 20},
         "route": _route("shortest", 100, 50)},
        {"route_type": "safe", "preference_score": None,
         "metrics": {"distance_m": 150, "stairs_distance_m": 0},
         "route": _route("safe", 150, 50)},
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates,
        [RoutePreference(factor="stairs_distance_m", direction="avoid"),
         RoutePreference(factor="distance_m", direction="minimize")],
    )
    assert unsupported == []
    assert selected["route_type"] == "safe"
    assert candidates[0]["preference_score"] is None


def test_no_step_free_candidate_does_not_masquerade_as_step_free() -> None:
    candidates = [
        {"route_type": "shortest", "preference_score": None,
         "metrics": {"stairs_distance_m": 10},
         "route": _route("shortest", 100, 50)},
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates,
        [RoutePreference(factor="stairs_distance_m", direction="avoid")],
    )
    assert selected is None
    assert unsupported[0].factor == "stairs_distance_m"
    assert "hard avoidance" in unsupported[0].reason


def test_unvalidated_population_metric_is_not_exposed(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_safe_route",
        lambda **_: _route("safe", 130, 90),
    )

    result = route_ranking_service.rank_route_candidates(
        _arguments(
            [{"factor": "population_score", "direction": "maximize", "weight": 1}]
        )
    )

    assert result["selected_route_type"] is None
    assert result["unsupported_preferences"][0].factor == "population_score"


def test_night_default_policy_prefers_well_lit_safe_route(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_safe_route",
        lambda **_: _route("safe", 130, 90),
    )

    day_result = route_ranking_service.rank_route_candidates(
        _arguments([], departure_time="14:00:00")
    )
    night_result = route_ranking_service.rank_route_candidates(
        _arguments([], departure_time="22:00:00")
    )

    assert day_result["selected_route_type"] == "shortest"
    assert night_result["selected_route_type"] == "safe"


def test_agent_endpoint_validates_and_returns_ranked_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_safe_route",
        lambda **_: _route("safe", 130, 90),
    )

    response = TestClient(app).post(
        "/api/agent/execute",
        json={
            "tool": "rank_routes",
            "arguments": {
                "origin": {"latitude": 37.46, "longitude": 126.67},
                "destination": {"latitude": 37.47, "longitude": 126.68},
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
    assert len(payload["candidates"]) == 3


def test_unverified_major_road_candidates_are_not_final_recommendations(monkeypatch) -> None:
    def unverified_route(route_type: str, distance: float, score: float):
        route = _route(route_type, distance, score)
        route["properties"]["unverified_major_road_count"] = 1
        return route

    monkeypatch.setattr(route_ranking_service, "get_shortest_route",
                        lambda **_: unverified_route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_balanced_route",
                        lambda **_: unverified_route("balanced", 115, 55))
    monkeypatch.setattr(route_ranking_service, "get_safe_route",
                        lambda **_: unverified_route("safe", 130, 90))

    result = route_ranking_service.rank_route_candidates(_arguments([]))

    assert result["selected_route_type"] is None
    assert result["selected_route"] is None
    assert result["recommendation_status"] == "field_review_required"
    assert len(result["candidates"]) == 3


def test_reviewed_candidate_can_be_selected_over_unverified_higher_score() -> None:
    reviewed = _route("shortest", 120, 40)
    unverified = _route("safe", 100, 90)
    unverified["properties"]["unverified_major_road_count"] = 1
    candidates = [
        {"route_type": "shortest", "preference_score": None,
         "metrics": {"safety_score": 40.0}, "route": reviewed},
        {"route_type": "safe", "preference_score": None,
         "metrics": {"safety_score": 90.0}, "route": unverified},
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, [RoutePreference(factor="safety_score", direction="maximize")],
    )
    assert unsupported == []
    assert selected["route_type"] == "shortest"
    assert candidates[1]["preference_score"] is None
