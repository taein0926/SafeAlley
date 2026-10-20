from datetime import time
from types import SimpleNamespace

import pytest

from app.schemas.agent import ParsedRouteIntent, RoutePreference
from app.services import local_llm_service as llm
from app.services.condition_cards import routing_condition_cards


@pytest.mark.parametrize("query,expected", [
    ("밤 열한 시에 출발할게", time(23)),
    ("오전 두 시 반에 출발", time(2, 30)),
    ("오후 열두 시에 출발", time(12)),
    ("밤 열 시가 아니라 밤 열한 시로 바꿔", time(23)),
])
def test_written_hour_preserves_and_validates_clock(query, expected):
    intent = ParsedRouteIntent(departure_time=expected)
    llm._discard_invented_time(query, intent)
    llm._correct_explicit_departure_time(query, intent)
    assert intent.departure_time == expected
    llm._validate_query_semantics(query, intent)


@pytest.mark.parametrize("query", ["밤에 출발", "오전 두 시까지 도착", "시간은 아직 미정"])
def test_vague_or_arrival_time_is_not_departure(query):
    intent = ParsedRouteIntent(departure_time=time(2))
    llm._discard_invented_time(query, intent)
    assert intent.departure_time is None


@pytest.mark.parametrize("direction,expected", [("minimize", "applied"), ("avoid", "not_applied")])
def test_partial_crossings_only_soft_cost_is_applied(direction, expected):
    selected = {"metrics": {"crosswalk_count": None}, "route": {"properties": {
        "crossing_data_available": False, "cost_weights": {"crossing": .5}, "total_crosswalk_count": 3}}}
    args = SimpleNamespace(stairs_weight=0, crossing_weight=0)
    preference = RoutePreference(factor="crosswalk_count", direction=direction)
    cards = routing_condition_cards(selected, [preference], [SimpleNamespace(factor="crosswalk_count")], args, SimpleNamespace(is_night=True))
    card = next(c for c in cards if c.factor == "crossing")
    assert card.state == expected
    if direction == "minimize":
        assert card.application_scope == "route_generation" and card.data_quality == "partial"
    assert selected["metrics"]["crosswalk_count"] is None


@pytest.mark.parametrize("query,retained", [
    ("도화역에서 주안역까지 안내해 줘", False),
    ("도화역에서 주안역까지 짧은 길", True),
    ("빨리 도착할 수 있는 길", True),
    ("너무 멀리 돌아가지 말아줘", True),
    ("밝은 길이 우선이고 너무 먼 길은 싫어", True),
])
def test_default_route_is_not_a_user_distance_preference(query, retained):
    intent = ParsedRouteIntent(preferences=[RoutePreference(factor="distance_m", direction="minimize")])
    llm._discard_unmentioned_distance(query, intent)
    assert bool(intent.preferences) is retained


def test_model_outage_is_not_replaced_with_another_model(monkeypatch):
    import httpx
    def fail(*args, **kwargs):
        raise httpx.ConnectError("unreachable")
    monkeypatch.setattr(llm.httpx, "post", fail)
    with pytest.raises(llm.LocalLLMUnavailableError, match="서비스 관리자"):
        llm._request_ollama({})


def test_internal_crossing_cost_does_not_light_an_unrequested_card():
    selected = {"metrics": {"crosswalk_count": 3}, "route": {"properties": {
        "crossing_data_available": True, "cost_weights": {"crossing": .5}, "total_crosswalk_count": 3}}}
    args = SimpleNamespace(preference_mode="explicit_only", departure_time=time(14), stairs_weight=0, crossing_weight=0)
    cards = routing_condition_cards(selected, [], [], args, SimpleNamespace(is_night=False))
    assert {c.factor for c in cards if c.state == "applied"} == {"time"}
