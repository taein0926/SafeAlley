from copy import deepcopy
from datetime import time
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.repositories.road_repository import NearestRoadNode
from app.schemas.agent import RouteOptimizationArguments, RoutePreference
from app.services import condition_cards, route_ranking_service, route_service
from app.services.route_metrics import calculate_route_metrics
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.weather_service import RouteTimeContext


@pytest.fixture
def prepared_graph(monkeypatch):
    settings = Settings(_env_file=None)
    monkeypatch.setattr(condition_cards, "get_settings", lambda: settings)
    monkeypatch.setattr(route_service, "get_settings", lambda: settings)
    graph = RoadGraph()
    graph.add_node(GraphNode(1, 0, 0))
    graph.add_node(GraphNode(2, 100, 0))
    graph.add_edge(GraphEdge(
        segment_id=1, source_id="test", name=None, from_node_id=1, to_node_id=2,
        distance_m=100, streetlight_score=80, cctv_score=60, help_point_score=0,
        population_score=0, safety_score=56,
        coordinates=((126.68, 37.46), (126.681, 37.461)),
        highway="footway", sidewalk_confirmed=True, pedestrian_version="test",
    ))
    prepared = route_service.PreparedRoute(
        graph, NearestRoadNode(1, 0, 0, 126.68, 37.46, 0),
        NearestRoadNode(2, 100, 0, 126.681, 37.461, 0), False,
    )
    monkeypatch.setattr(route_ranking_service, "prepare_route", lambda **_: prepared)
    monkeypatch.setattr(route_ranking_service, "resolve_route_time", lambda departure:
                        RouteTimeContext(departure, departure == time(22), "fallback"))
    return prepared, settings


@pytest.mark.parametrize("hour", [14, 22])
@pytest.mark.parametrize("safety", [0, 50, 100])
def test_direct_settings_expand_aggregate_into_used_components(prepared_graph, hour, safety):
    preferences = []
    if safety < 100:
        preferences.append(RoutePreference(factor="distance_m", direction="minimize", weight=100 - safety))
    if safety:
        preferences.append(RoutePreference(factor="safety_score", direction="maximize", weight=safety))
    args = RouteOptimizationArguments(
        origin={"latitude": 37.46, "longitude": 126.68},
        destination={"latitude": 37.461, "longitude": 126.681},
        departure_time=time(hour), preferences=preferences,
        stairs_weight=0, crossing_weight=1,
    )
    result = route_ranking_service.rank_route_candidates(args)
    cards = {card.factor: card for card in result["recommendation_conditions"]}
    assert cards["streetlight"].state == ("applied" if safety and hour == 22 else "not_applied")
    assert cards["cctv"].state == cards["safety"].state == ("applied" if safety else "not_applied")
    assert cards["stairs"].state == "not_applied"
    assert cards["crossing"].state == "applied"
    if safety:
        assert "안전시설 접근성" in cards["safety"].reason
    if hour == 14:
        assert "낮에는" in cards["streetlight"].reason
    # A zero help-facility score is valid data, not evidence that its weight was omitted.
    assert result["selected_route"]["properties"]["road_segments"][0]["help_point_score"] == 0


def _selected(prepared_graph, hour=22):
    prepared, _ = prepared_graph
    route = route_service.get_safe_route(
        start_longitude=126.68, start_latitude=37.46,
        end_longitude=126.681, end_latitude=37.461, prepared=prepared,
        time_context=RouteTimeContext(time(hour), hour == 22, "fallback"),
    )
    return {"route": route, "metrics": calculate_route_metrics(route)}


def _cards(selected, preferences, *, hour=22, unsupported=()):
    args = SimpleNamespace(stairs_weight=0, crossing_weight=0, preference_mode="explicit_only")
    return {card.factor: card for card in condition_cards.routing_condition_cards(
        selected, preferences, unsupported, args, SimpleNamespace(is_night=hour == 22),
    )}


@pytest.mark.parametrize("metric,enabled", [("streetlight_score", "streetlight"), ("cctv_score", "cctv")])
def test_single_facility_request_does_not_enable_unrequested_facilities(prepared_graph, metric, enabled):
    cards = _cards(_selected(prepared_graph), [RoutePreference(factor=metric, direction="maximize")])
    assert {factor for factor, card in cards.items() if card.state == "applied"} == {enabled}


def test_daytime_forces_streetlight_off_even_if_caller_passes_unfiltered_preferences(prepared_graph):
    cards = _cards(_selected(prepared_graph), [RoutePreference(factor="streetlight_score", direction="maximize")], hour=14)
    assert cards["streetlight"].state == "not_applied"


def test_aggregate_requires_supported_data_without_mutating_scores(prepared_graph):
    selected = _selected(prepared_graph)
    preferences = [RoutePreference(factor="safety_score", direction="maximize")]
    selected["route"]["properties"]["road_segments"][0].pop("help_point_score")
    before = deepcopy(selected)
    cards = _cards(selected, preferences)
    assert cards["safety"].state == "not_applied"
    assert cards["streetlight"].state == cards["cctv"].state == "applied"
    assert selected == before
    cards = _cards(selected, preferences, unsupported=[SimpleNamespace(factor="safety_score")])
    assert all(card.state == "not_applied" for card in cards.values())
    assert all(card.state == "not_applied" for card in _cards(None, preferences).values())


def test_disabled_help_facility_weight_does_not_enable_safety_card(prepared_graph):
    _, settings = prepared_graph
    settings.safety_help_point_weight = 0
    cards = _cards(_selected(prepared_graph, 14), [RoutePreference(factor="safety_score", direction="maximize")], hour=14)
    assert cards["safety"].state == cards["streetlight"].state == "not_applied"
    assert cards["cctv"].state == "applied"


def test_missing_streetlight_data_does_not_enable_streetlight_card(prepared_graph):
    selected = _selected(prepared_graph)
    selected["route"]["properties"]["road_segments"][0]["streetlight_data_available"] = False
    cards = _cards(selected, [RoutePreference(factor="safety_score", direction="maximize")])
    assert cards["streetlight"].state == "not_applied"
    assert cards["cctv"].state == cards["safety"].state == "applied"
