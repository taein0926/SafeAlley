from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.agent import RouteOptimizationArguments, RoutePreference
from app.services import route_ranking_service
from app.services.weather_service import RouteTimeContext


@pytest.fixture(autouse=True)
def custom_route_candidate(monkeypatch) -> None:
    monkeypatch.setattr(route_ranking_service, "resolve_route_time", lambda departure: RouteTimeContext(
        departure or time(14), (departure or time(14)) >= time(20) or (departure or time(14)) < time(6), "fallback",
    ))
    monkeypatch.setattr(route_ranking_service, "prepare_route", lambda **_: None)
    monkeypatch.setattr(
        route_ranking_service,
        "get_custom_route",
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


@pytest.mark.parametrize("direction, expected", [("minimize", "custom"), ("avoid", None)])
def test_partial_crossing_cost_is_usable_but_never_claims_hard_avoidance(monkeypatch, direction, expected):
    shortest = _route("shortest", 100, 20)
    custom = _route("custom", 110, 20)
    for route in (shortest, custom):
        route["properties"].update(crossing_data_available=False, pedestrian_metadata_coverage_percent=100)
    custom["properties"]["cost_weights"]["crossing"] = 1
    monkeypatch.setattr(route_ranking_service, "get_shortest_route", lambda **_: shortest)
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: custom)
    result = route_ranking_service.rank_route_candidates(_arguments([
        {"factor": "crosswalk_count", "direction": direction, "weight": 1},
    ]))
    assert result["selected_route_type"] == expected
    assert all(c["metrics"]["crosswalk_count"] is None for c in result["candidates"])
    if expected:
        assert result["recommendation_factors"] == ["crossing"]
        assert "확인할 수 없어요" in result["recommendation_reason"]


def test_daytime_secondary_safety_reason_does_not_claim_streetlight_usage(monkeypatch):
    monkeypatch.setattr(route_ranking_service, "get_shortest_route", lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: _route("custom", 110, 90))
    result = route_ranking_service.rank_route_candidates(_arguments([
        {"factor": "distance_m", "direction": "minimize", "weight": 50},
        {"factor": "safety_score", "direction": "maximize", "weight": 50},
    ], departure_time="12:00:00"))
    assert "가로등" not in result["recommendation_reason"]
    assert "CCTV·도움시설" in result["recommendation_reason"]


def test_ranking_combines_registered_metrics(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_custom_route",
        lambda **_: _route("custom", 130, 90),
    )

    result = route_ranking_service.rank_route_candidates(
        _arguments(
            [
                {"factor": "distance_m", "direction": "minimize", "weight": 1},
                {"factor": "streetlight_score", "direction": "maximize", "weight": 3},
            ], departure_time="22:00:00",
        )
    )

    assert result["selected_route_type"] == "custom"
    assert result["unsupported_preferences"] == []
    assert "가로등과의 거리·주변 밀도·가로등이 드문 구간" in result["recommendation_reason"]
    assert "최단 경로보다 조건이 좋아" in result["recommendation_reason"]
    assert "최단 경로보다 약 30m 더 걸어요" in result["recommendation_reason"]
    assert result["compared_route_type"] == "shortest"
    criteria = {item["factor"]: item for item in result["recommendation_criteria"]}
    assert criteria["streetlight_score"]["outcome"] == "better"
    assert criteria["streetlight_score"]["confidence"] == "medium"
    assert criteria["distance_m"]["outcome"] == "worse"
    assert criteria["distance_m"]["confidence"] == "high"
    assert any("추천 경로 130m, 최단 경로 100m" in note
               for note in result["recommendation_notes"])
    assert any("실제 치안" in note for note in result["recommendation_notes"])


def test_cctv_explanation_uses_plain_language_without_claiming_device_count(monkeypatch) -> None:
    monkeypatch.setattr(route_ranking_service, "get_shortest_route",
                        lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route",
                        lambda **_: _route("custom", 130, 90))

    result = route_ranking_service.rank_route_candidates(
        _arguments([{"factor": "cctv_score", "direction": "maximize", "weight": 1}])
    )

    reason = result["recommendation_reason"]
    assert result["selected_route_type"] == "custom"
    assert "CCTV와의 거리·주변 밀도·CCTV가 드문 구간" in reason
    assert "최단 경로보다 조건이 좋아" in reason
    assert "최단 경로보다 약 30m 더 걸어요" in reason
    assert "더 안전" not in reason
    assert "지표" not in reason
    assert "CCTV가 더 많" not in reason


def test_explanation_does_not_compare_with_excluded_route_or_exaggerate_small_gap(monkeypatch) -> None:
    excluded = _route("balanced", 1959, 55)
    excluded["properties"]["unverified_major_road_count"] = 5
    monkeypatch.setattr(route_ranking_service, "get_shortest_route",
                        lambda **_: _route("shortest", 1292.5, 45))
    monkeypatch.setattr(route_ranking_service, "get_custom_route",
                        lambda **_: _route("custom", 1296.77, 48))
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: excluded)

    result = route_ranking_service.rank_route_candidates(
        _arguments([{"factor": "distance_m", "direction": "minimize", "weight": 1}])
    )

    assert result["recommendation_status"] == "ready"
    assert result["selected_route_type"] == "shortest"
    assert result["recommendation_reason"] == (
        "거리를 우선해 약 1.29km 길을 골랐어요."

    )
    assert any("다른 길 1개" in note for note in result["recommendation_notes"])
    assert result["compared_route_type"] is None
    assert all("1959" not in text and "100점" not in text
               for text in [result["recommendation_reason"], *result["recommendation_notes"]])


def test_unknown_metrics_are_reported_without_substitution(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_custom_route",
        lambda **_: _route("custom", 130, 90),
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
    assert result["recommendation_status"] == "no_supported_preferences"
    assert "자료가 부족해" in result["recommendation_reason"]
    assert any("계단" in note for note in result["recommendation_notes"])
    assert {item["outcome"] for item in result["recommendation_criteria"]} == {"unavailable"}


def test_registered_metric_without_candidate_data_is_not_scored() -> None:
    candidates = [
        {
            "route_type": "shortest",
            "preference_score": None,
            "metrics": {"streetlight_score": None},
            "route": _route("shortest", 100, 20),
        },
        {
            "route_type": "custom",
            "preference_score": None,
            "metrics": {"streetlight_score": 80.0},
            "route": _route("custom", 120, 80),
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
        {"route_type": "custom", "preference_score": None,
         "metrics": {"distance_m": 150, "stairs_distance_m": 0},
         "route": _route("custom", 150, 50)},
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates,
        [RoutePreference(factor="stairs_distance_m", direction="avoid"),
         RoutePreference(factor="distance_m", direction="minimize")],
    )
    assert unsupported == []
    assert selected["route_type"] == "custom"
    assert candidates[0]["preference_score"] is None


def test_equal_step_free_candidates_choose_shortest_and_explain_tie() -> None:
    candidates = [
        {"route_type": route_type, "preference_score": None,
         "metrics": {"distance_m": distance, "stairs_distance_m": 0},
         "route": _route(route_type, distance, 50)}
        for route_type, distance in (("shortest", 100), ("custom", 105))
    ]
    preference = RoutePreference(factor="stairs_distance_m", direction="avoid")

    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, [preference],
    )
    assert unsupported == []
    assert selected is candidates[0]

    reason, _ = route_ranking_service._recommendation_explanation(
        selected, candidates, [preference], [], "ready", None,
    )
    assert "비교한 경로 모두 지도 자료상 계단 구간이 없어서" in reason
    assert "가장 짧은 길" in reason
    assert "계단 구간을 피하는 조건" not in reason


@pytest.mark.parametrize(
    ("factor", "expected"),
    [
        ("crosswalk_count", "지도 자료상 건널목 수가 0개여서"),
        ("sidewalk_coverage_percent", "확인된 보행공간 비율이 0%여서"),
    ],
)
def test_equal_zero_metrics_are_not_claimed_as_ranking_advantages(
    factor: str, expected: str,
) -> None:
    candidates = [
        {"route_type": route_type, "preference_score": None,
         "metrics": {"distance_m": distance, factor: 0},
         "route": _route(route_type, distance, 50)}
        for route_type, distance in (("shortest", 100), ("custom", 105))
    ]
    preference = RoutePreference(
        factor=factor,
        direction="minimize" if factor == "crosswalk_count" else "maximize",
    )
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, [preference],
    )
    assert selected is candidates[0]
    assert unsupported == []
    reason, _ = route_ranking_service._recommendation_explanation(
        selected, candidates, [preference], [], "ready", None,
    )
    assert expected in reason
    assert "가장 짧은 길" in reason
    assert "비교해 약" not in reason
    assert "참고해 약" not in reason
    notes = route_ranking_service._recommendation_explanation(
        selected, candidates, [preference], [], "ready", None,
    )[1]
    assert any(
        ("실제 부재를 확인한 것은 아닙니다" if factor == "crosswalk_count"
         else "실제 보도가 없다는 뜻은 아닙니다") in note
        for note in notes
    )


def test_cctv_and_stairs_explanation_mentions_step_free_tie() -> None:
    candidates = [
        {"route_type": route_type, "preference_score": None,
         "metrics": {"distance_m": distance, "cctv_score": score,
                     "stairs_distance_m": 0},
         "route": _route(route_type, distance, score)}
        for route_type, distance, score in (
            ("shortest", 100, 20), ("custom", 130, 90)
        )
    ]
    preferences = [
        RoutePreference(factor="cctv_score", direction="maximize"),
        RoutePreference(factor="stairs_distance_m", direction="avoid"),
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, preferences,
    )
    assert selected is candidates[1]
    assert unsupported == []
    reason, _ = route_ranking_service._recommendation_explanation(
        selected, candidates, preferences, [], "ready", None,
    )
    assert "CCTV와의 거리·주변 밀도·CCTV가 드문 구간" in reason
    assert "두 경로 모두 지도에 기록된 계단 구간은 0m예요" in reason
    notes = route_ranking_service._recommendation_explanation(
        selected, candidates, preferences, [], "ready", None,
    )[1]
    assert any("계단 구간: 추천 경로 0m, 최단 경로 0m" in note for note in notes)
    assert any("현장에 계단이 없음을 보장하지 않습니다" in note for note in notes)


def test_distance_and_cctv_tradeoff_does_not_claim_cctv_advantage() -> None:
    candidates = [
        {"route_type": route_type, "preference_score": None,
         "metrics": {"distance_m": distance, "cctv_score": score},
         "route": _route(route_type, distance, score)}
        for route_type, distance, score in (
            ("shortest", 100, 20), ("custom", 130, 90)
        )
    ]
    preferences = [
        RoutePreference(factor="distance_m", direction="minimize", weight=2),
        RoutePreference(factor="cctv_score", direction="maximize", weight=1),
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, preferences,
    )
    assert selected is candidates[0]
    assert unsupported == []
    reason, notes = route_ranking_service._recommendation_explanation(
        selected, candidates, preferences, [], "ready", None,
    )
    assert "다만 CCTV와의 거리·주변 밀도·분포 공백만 보면 맞춤 경로이 더 유리해요" in reason
    assert "이 길이 더 유리" not in reason
    assert any("CCTV와의 거리·주변 밀도·분포 공백: 맞춤 경로이 더 유리합니다" in note
               for note in notes)


@pytest.mark.parametrize(
    ("factor", "selected_value", "other_value", "expected"),
    [
        ("stairs_distance_m", 0, 18, "계단 구간은 다른 길보다 약 18m 짧아요"),
        (
            "crosswalk_count", 1, 2,
            "지도에 기록된 건널목은 다른 길보다 1개 적어요",
        ),
        ("max_slope_percent", 2.5, 6.0, "최대 경사는 다른 길보다 3.5%p 낮아요"),
    ],
)
def test_secondary_explanation_covers_accessibility_metrics(
    factor: str,
    selected_value: float,
    other_value: float,
    expected: str,
) -> None:
    selected = {"metrics": {factor: selected_value}}
    comparison = {"metrics": {factor: other_value}}
    preference = RoutePreference(factor=factor, direction="minimize")

    detail = route_ranking_service._secondary_condition_sentence(
        preference, selected, comparison,
    )

    assert detail is not None
    assert expected in detail


def test_proxy_evidence_explains_inputs_without_exposing_abstract_score() -> None:
    selected = {"metrics": {"cctv_score": 72}}
    comparison = {"metrics": {"cctv_score": 58}}

    note = route_ranking_service._metric_evidence_note(
        RoutePreference(factor="cctv_score", direction="maximize"),
        selected,
        comparison,
    )

    assert note == "CCTV와의 거리·주변 밀도·분포 공백: 추천 경로가 더 유리합니다."
    assert "점수" not in note
    assert "지표" not in note


@pytest.mark.parametrize(
    ("factor", "selected_value", "other_value", "expected"),
    [
        ("stairs_distance_m", 0, 18, "계단 구간이 맞춤 경로보다 약 18m 짧아"),
        (
            "crosswalk_count", 1, 2,
            "지도에 기록된 건널목이 맞춤 경로보다 1개 적어",
        ),
        ("max_slope_percent", 2.5, 6.0, "최대 경사가 맞춤 경로보다 3.5%p 낮아"),
    ],
)
def test_primary_accessibility_metric_uses_plain_comparison(
    factor: str,
    selected_value: float,
    other_value: float,
    expected: str,
) -> None:
    candidates = [
        {
            "route_type": "shortest",
            "preference_score": None,
            "metrics": {"distance_m": 110, factor: selected_value},
            "route": _route("shortest", 110, 50),
        },
        {
            "route_type": "custom",
            "preference_score": None,
            "metrics": {"distance_m": 100, factor: other_value},
            "route": _route("custom", 100, 50),
        },
    ]
    preference = RoutePreference(factor=factor, direction="minimize")
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, [preference],
    )

    reason, _ = route_ranking_service._recommendation_explanation(
        selected, candidates, [preference], unsupported, "ready", None,
    )

    assert expected in reason
    assert "값이 더" not in reason


def test_distance_primary_does_not_call_a_longer_route_nearly_equal() -> None:
    candidates = [
        {"route_type": route_type, "preference_score": None,
         "metrics": {"distance_m": distance, "cctv_score": score,
                     "streetlight_score": score},
         "route": _route(route_type, distance, score)}
        for route_type, distance, score in (
            ("shortest", 100, 20), ("custom", 130, 90)
        )
    ]
    preferences = [
        RoutePreference(factor="distance_m", direction="minimize", weight=2),
        RoutePreference(factor="cctv_score", direction="maximize", weight=1.5),
        RoutePreference(factor="streetlight_score", direction="maximize", weight=1.5),
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, preferences,
    )
    assert selected is candidates[1]
    assert unsupported == []
    reason, _ = route_ranking_service._recommendation_explanation(
        selected, candidates, preferences, [], "ready", None,
    )
    assert "약 30m 더 걸리지만" in reason
    assert "거의 같아요" not in reason


def test_missing_crosswalk_data_is_not_described_as_zero() -> None:
    candidate = {
        "route_type": "shortest", "preference_score": None,
        "metrics": {"distance_m": 100, "crosswalk_count": None},
        "route": _route("shortest", 100, 50),
    }
    preference = RoutePreference(factor="crosswalk_count", direction="minimize")
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        [candidate], [preference],
    )
    assert selected is None
    reason, notes = route_ranking_service._recommendation_explanation(
        selected, [candidate], [preference], unsupported,
        "no_supported_preferences", None,
    )
    assert "자료가 부족해" in reason
    assert any("검증된 측정값이 없어" in note for note in notes)
    assert all("0개" not in text for text in [reason, *notes])


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
        "get_custom_route",
        lambda **_: _route("custom", 130, 90),
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
        "get_custom_route",
        lambda **_: _route("custom", 130, 90),
    )

    day_result = route_ranking_service.rank_route_candidates(
        _arguments([], departure_time="14:00:00")
    )
    night_result = route_ranking_service.rank_route_candidates(
        _arguments([], departure_time="22:00:00")
    )

    assert day_result["selected_route_type"] == "shortest"
    assert night_result["selected_route_type"] == "custom"


def test_daytime_ignores_even_explicit_streetlight_preference(monkeypatch):
    monkeypatch.setattr(route_ranking_service, "get_shortest_route", lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: _route("custom", 130, 90))
    result = route_ranking_service.rank_route_candidates(_arguments(
        [{"factor": "streetlight_score", "direction": "maximize", "weight": 100}],
        departure_time="14:00:00",
    ))
    assert result["selected_route_type"] == "shortest"
    assert result["unsupported_preferences"][0].reason == "Excluded during daylight"
    assert result["recommendation_factors"] == ["distance"]
    assert any("가로등 조건" in note for note in result["recommendation_notes"])


def test_daytime_safety_explanation_excludes_lighting(monkeypatch):
    monkeypatch.setattr(route_ranking_service, "get_shortest_route", lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: _route("custom", 130, 90))
    result = route_ranking_service.rank_route_candidates(_arguments(
        [{"factor": "safety_score", "direction": "maximize"}], departure_time="14:00:00",
    ))
    assert "CCTV·도움시설" in result["recommendation_reason"]
    assert "가로등" not in result["recommendation_reason"]
    safety = next(item for item in result["recommendation_criteria"] if item["factor"] == "safety_score")
    assert "가로등" not in safety["summary"]
    assert "가로등" not in safety["confidence_reason"]


def test_solar_night_drives_ranking_before_the_old_20_hour_boundary(monkeypatch):
    monkeypatch.setattr(route_ranking_service, "resolve_route_time", lambda _: RouteTimeContext(time(19), True, "official_solar"))
    monkeypatch.setattr(route_ranking_service, "get_shortest_route", lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route", lambda **_: _route("custom", 130, 90))
    result = route_ranking_service.rank_route_candidates(_arguments([], departure_time="19:00:00"))
    assert result["selected_route_type"] == "custom"
    assert any("밤 시간" in note for note in result["recommendation_notes"])


def test_agent_endpoint_validates_and_returns_ranked_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        route_ranking_service,
        "get_shortest_route",
        lambda **_: _route("shortest", 100, 20),
    )
    monkeypatch.setattr(
        route_ranking_service,
        "get_custom_route",
        lambda **_: _route("custom", 130, 90),
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
    assert payload["selected_route_type"] == "custom"
    assert len(payload["candidates"]) == 2
    assert payload["recommendation_reason"]
    assert payload["recommendation_notes"]


def test_unverified_major_road_candidates_are_not_final_recommendations(monkeypatch) -> None:
    def unverified_route(route_type: str, distance: float, score: float):
        route = _route(route_type, distance, score)
        route["properties"]["unverified_major_road_count"] = 1
        return route

    monkeypatch.setattr(route_ranking_service, "get_shortest_route",
                        lambda **_: unverified_route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route",
                        lambda **_: unverified_route("balanced", 115, 55))
    monkeypatch.setattr(route_ranking_service, "get_custom_route",
                        lambda **_: unverified_route("custom", 130, 90))

    result = route_ranking_service.rank_route_candidates(_arguments([]))

    assert result["selected_route_type"] is None
    assert result["selected_route"] is None
    assert result["recommendation_status"] == "field_review_required"
    assert len(result["candidates"]) == 2
    assert "자동 추천을 보류" in result["recommendation_reason"]
    assert any("위험하다는 뜻은 아닙니다" in note for note in result["recommendation_notes"])
    assert result["recommendation_criteria"][0]["outcome"] == "unavailable"
    assert "추천 경로가 확정되지 않아" in result["recommendation_criteria"][0]["summary"]


def test_missing_dem_is_not_described_as_a_flat_route(monkeypatch) -> None:
    monkeypatch.setattr(route_ranking_service, "get_shortest_route",
                        lambda **_: _route("shortest", 100, 20))
    monkeypatch.setattr(route_ranking_service, "get_custom_route",
                        lambda **_: _route("custom", 130, 90))

    result = route_ranking_service.rank_route_candidates(
        _arguments([{"factor": "max_slope_percent", "direction": "minimize", "weight": 1}])
    )

    assert result["selected_route_type"] is None
    assert result["recommendation_status"] == "no_supported_preferences"
    assert any("DEM은 현재 적재되지 않았습니다" in note for note in result["recommendation_notes"])
    assert "평지" not in result["recommendation_reason"]


def test_reviewed_candidate_can_be_selected_over_unverified_higher_score() -> None:
    reviewed = _route("shortest", 120, 40)
    unverified = _route("custom", 100, 90)
    unverified["properties"]["unverified_major_road_count"] = 1
    candidates = [
        {"route_type": "shortest", "preference_score": None,
         "metrics": {"safety_score": 40.0}, "route": reviewed},
        {"route_type": "custom", "preference_score": None,
         "metrics": {"safety_score": 90.0}, "route": unverified},
    ]
    selected, unsupported = route_ranking_service.rank_generated_candidates(
        candidates, [RoutePreference(factor="safety_score", direction="maximize")],
    )
    assert unsupported == []
    assert selected["route_type"] == "shortest"
    assert candidates[1]["preference_score"] is None
