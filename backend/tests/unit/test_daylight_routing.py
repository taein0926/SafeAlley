from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest

from app.repositories.road_repository import NearestRoadNode
from app.repositories.weather_repository import WeatherReadError
from app.services import weather_service
from app.services.route_metrics import calculate_route_metrics
from app.services.route_service import PreparedRoute, get_safe_route
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.routing.safety_cost import SafetyCostPolicy
from app.services.weather_service import KST, RouteTimeContext


def edge(segment_id=1, start=1, end=2, length=100, light=0):
    return GraphEdge(
        segment_id=segment_id, source_id=str(segment_id), name=None,
        from_node_id=start, to_node_id=end, distance_m=length,
        streetlight_score=light, cctv_score=60, help_point_score=30,
        population_score=0, safety_score=0.4 * light + 30,
        coordinates=((126.68, 37.46), (126.681, 37.461)),
    )


def test_day_cost_does_not_change_when_only_lighting_changes():
    dark = edge()
    lit = edge(light=100)
    day = SafetyCostPolicy(1, 5, streetlight_included=False)
    night = SafetyCostPolicy(1, 5, streetlight_included=True)
    assert day.effective_safety_score(dark) == pytest.approx(50)
    assert day.edge_cost(dark) == day.edge_cost(lit)
    assert night.edge_cost(lit) < night.edge_cost(dark)
    assert day.effective_safety_score(replace(dark, cctv_score=90)) > 50
    assert day.effective_safety_score(replace(dark, help_point_score=90)) > 50


@pytest.mark.parametrize("stairs,intersection", [(0, 0), (1, 1)])
def test_daylight_does_not_remove_stair_or_intersection_penalties(stairs, intersection):
    road = replace(edge(), is_steps=True, intersection_exposure_m=30)
    day = SafetyCostPolicy(1, 5, stairs, intersection, streetlight_included=False)
    night = SafetyCostPolicy(1, 5, stairs, intersection)
    assert day.breakdown(road).stairs_penalty == night.breakdown(road).stairs_penalty
    assert day.breakdown(road).intersection_penalty == night.breakdown(road).intersection_penalty


def test_day_and_night_routes_reuse_graph_without_mutating_stored_scores():
    graph = RoadGraph()
    for node in [GraphNode(1, 0, 0), GraphNode(2, 100, 0), GraphNode(3, 50, 20)]:
        graph.add_node(node)
    graph.add_edge(edge())
    graph.add_edge(edge(2, 1, 3, 60, 100))
    graph.add_edge(edge(3, 3, 2, 60, 100))
    start = NearestRoadNode(1, 0, 0, 126.68, 37.46, 0)
    end = NearestRoadNode(2, 100, 0, 126.681, 37.461, 0)
    prepared = PreparedRoute(graph, start, end, False)
    kwargs = dict(start_longitude=126.68, start_latitude=37.46,
                  end_longitude=126.681, end_latitude=37.461, prepared=prepared)
    day_context = RouteTimeContext(time(14), False, "fallback")
    night = get_safe_route(**kwargs, time_context=RouteTimeContext(time(22), True, "fallback"))
    day = get_safe_route(**kwargs, time_context=day_context)
    assert day == get_safe_route(**kwargs, time_context=day_context)
    assert [s["id"] for s in day["properties"]["road_segments"]] == [1]
    assert [s["id"] for s in night["properties"]["road_segments"]] == [2, 3]
    assert day["properties"]["average_safety_score"] == pytest.approx(50)
    assert day["properties"]["road_segments"][0]["safety_score"] == pytest.approx(50)
    assert day["properties"]["streetlight_included"] is False
    assert night["properties"]["streetlight_included"] is True
    assert graph.neighbors(1)[0].safety_score == 30
    assert calculate_route_metrics(day)["streetlight_score"] is None
    assert calculate_route_metrics(night)["streetlight_score"] == 100


@pytest.mark.parametrize("departure,night", [(time(6, 19), True), (time(6, 20), False),
                                            (time(18, 29), False), (time(18, 30), True)])
def test_route_time_matches_the_weather_theme(monkeypatch, departure, night):
    now = datetime(2026, 9, 23, 14, tzinfo=KST)
    solar = {"solar_date": now.date(), "location": "인천", "sunrise": time(6, 20), "sunset": time(18, 30)}
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (None, solar))
    resolved = weather_service.resolve_route_time(departure, now=now)
    assert resolved.is_night is night
    assert resolved.theme_source == "official_solar"
    assert resolved.is_night == weather_service.get_weather(departure, now=now).is_night


@pytest.mark.parametrize("hour,night", [(0, True), (5, True), (6, False), (19, False), (20, True)])
def test_missing_or_unavailable_solar_uses_current_korea_time(monkeypatch, hour, night):
    now = datetime(2026, 9, 23, hour, tzinfo=KST)
    for reader in [lambda *_: (None, None), lambda *_: (_ for _ in ()).throw(WeatherReadError())]:
        monkeypatch.setattr(weather_service, "read_weather", reader)
        result = weather_service.resolve_route_time(None, now=now)
        assert result.departure_time == time(hour)
        assert result.is_night is night
        assert result.theme_source == "fallback"


def test_stale_solar_not_used_for_daylight_routing(monkeypatch):
    now = datetime(2026, 9, 23, 19, tzinfo=KST)
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (None, {
        "solar_date": now.date() - timedelta(days=1), "location": "인천",
        "sunrise": time(6, 20), "sunset": time(18, 30),
    }))
    assert weather_service.resolve_route_time(None, now=now).is_night is False
