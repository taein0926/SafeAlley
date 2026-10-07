from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import app
from app.schemas.agent import RoutePreference
from app.services.condition_cards import routing_condition_cards
from app.services import jev_preview_service as service


@pytest.fixture(autouse=True)
def state(monkeypatch):
    service.reset_preview_state()
    settings = SimpleNamespace(jev_preview_enabled=True, typesafe_api_key=SecretStr("test-key"),
        jev_preview_model="jev-test", jev_preview_min_confidence=.7)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "monotonic", lambda: 100.0)
    yield settings
    service.reset_preview_state()


def _response(payload, choices=None):
    choices = choices or {}
    return {"model": "jev-test", "usage": {"input_tokens": 100}, "answers": {
        factor: {"type": "choice", "choice": choices.get(factor, "skip"), "confidence": .95}
        for factor in payload["questions"]
    }}


def test_disabled_preview_does_not_call_external_api(monkeypatch, state):
    state.jev_preview_enabled = False
    monkeypatch.setattr(service.httpx, "post", lambda *a, **k: pytest.fail("unexpected paid call"))
    client = TestClient(app)
    assert client.get("/api/agent/intent-preview/status").json()["available"] is False
    response = client.post("/api/agent/intent-preview", json={"query": "계단 피하기"})
    assert response.status_code == 503
    assert "remaining_calls" not in client.get("/api/agent/intent-preview/status").json()


def test_jev_questions_keep_full_query_and_exactly_eight_cards():
    payload = service.build_request("계단은 피하지 않아도 돼. CCTV가 많은 길", "jev-test")
    assert payload["state"] == "계단은 피하지 않아도 돼. CCTV가 많은 길"
    assert len(payload["questions"]) == 8
    cards = service.parse_decisions(payload, _response(payload, {"cctv": "apply", "time": "night"}), .7)
    assert {card.factor: card.state for card in cards}["stairs"] == "not_applied"
    assert {card.factor: card.state for card in cards}["cctv"] == "applied"
    assert cards[-1].period == "night"


def test_incomplete_or_uncertain_answers_remain_analyzing():
    payload = service.build_request("계단을", "jev-test")
    response = _response(payload, {"stairs": "pending", "streetlight": "apply"})
    response["answers"]["streetlight"]["confidence"] = .55
    cards = {card.factor: card for card in service.parse_decisions(payload, response, .7)}
    assert cards["stairs"].state == "analyzing"
    assert cards["streetlight"].state == "not_applied"
    assert cards["streetlight"].direction is None


@pytest.mark.parametrize("choice,direction,state", [
    ("apply", "maximize", "applied"), ("avoid", "avoid", "applied"),
    ("minimize", "minimize", "applied"), ("skip", None, "not_applied"),
    ("pending", None, "analyzing"),
])
def test_bridge_preview_reads_its_own_choice_without_assuming_stairs(choice, direction, state):
    payload = service.build_request("육교를 이용하는 길로 안내해줘", "jev-test")
    cards = {card.factor: card for card in service.parse_decisions(payload, _response(payload, {"bridge": choice}), .7)}
    assert cards["bridge"].state == state
    assert cards["bridge"].direction == direction
    assert cards["stairs"].state == "not_applied"


@pytest.mark.parametrize("choice", ["avoid", "minimize"])
@pytest.mark.parametrize("bridge_choice,bridge_state,bridge_direction", [
    ("skip", "not_applied", None), ("pending", "analyzing", None),
    ("apply", "applied", "maximize"), ("avoid", "applied", "avoid"),
    ("minimize", "applied", "minimize"),
])
def test_selected_crossing_preserves_independent_bridge_choice(choice, bridge_choice, bridge_state, bridge_direction):
    payload = service.build_request("건널목을 적게 건너는 길로 안내해줘", "jev-test")
    cards = {card.factor: card for card in service.parse_decisions(
        payload, _response(payload, {"crossing": choice, "bridge": bridge_choice}), .7)}
    assert cards["crossing"].direction == choice
    assert cards["bridge"].state == bridge_state
    assert cards["bridge"].direction == bridge_direction
    assert cards["bridge"].judgment == bridge_choice
    assert cards["stairs"].state == cards["cctv"].state == "not_applied"


@pytest.mark.parametrize("choice,confidence", [("skip", .95), ("pending", .95), ("minimize", .55)])
def test_unselected_or_uncertain_crossing_does_not_select_bridge(choice, confidence):
    payload = service.build_request("건널목", "jev-test")
    response = _response(payload, {"crossing": choice})
    response["answers"]["crossing"]["confidence"] = confidence
    cards = {card.factor: card for card in service.parse_decisions(payload, response, .7)}
    assert cards["crossing"].state != "applied"
    assert cards["bridge"].state == "not_applied"


def test_preview_api_and_cache_do_not_select_bridge_from_crossing(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"]["state"])
        return httpx.Response(200, request=httpx.Request("POST", url),
                              json=_response(kwargs["json"], {"crossing": "minimize"}))
    monkeypatch.setattr(service.httpx, "post", post)
    client = TestClient(app)
    for cached in (False, True):
        response = client.post("/api/agent/intent-preview", json={"query": "건널목을 적게 건너는 길로 안내해줘"})
        assert response.status_code == 200
        body = response.json()
        assert body["cached"] is cached
        cards = {card["factor"]: card for card in body["conditions"]}
        assert cards["crossing"]["state"] == "applied"
        assert cards["bridge"]["state"] == "not_applied"
        assert cards["bridge"]["direction"] is None
    assert len(calls) == 1


def test_negative_choice_does_not_leave_unrequested_card_spinning():
    payload = service.build_request("계단을 피하고", "jev-test")
    response = _response(payload, {"stairs": "avoid"})
    response["answers"]["safety"]["confidence"] = .3
    cards = {card.factor: card for card in service.parse_decisions(payload, response, .7)}
    assert cards["safety"].state == "not_applied"
    assert cards["safety"].judgment == "skip"
    assert cards["stairs"].state == "applied"


def test_duplicate_query_is_cached_without_a_cumulative_call_cap(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"]["state"])
        return httpx.Response(200, request=httpx.Request("POST", url), json=_response(kwargs["json"], {"stairs": "avoid"}))
    monkeypatch.setattr(service.httpx, "post", post)
    first = service.analyze_preview("계단 없이 가줘")
    second = service.analyze_preview("계단 없이 가줘")
    assert not first.cached and second.cached
    assert calls == ["계단 없이 가줘"]
    monkeypatch.setattr(service, "monotonic", lambda: 101.0)
    service.analyze_preview("CCTV 많은 길")
    assert calls == ["계단 없이 가줘", "CCTV 많은 길"]
    assert service.preview_status().available


def test_failures_are_not_retried_or_counted_against_a_cumulative_budget(monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError("test outage")
    monkeypatch.setattr(service.httpx, "post", fail)
    with pytest.raises(service.PreviewUnavailable):
        service.analyze_preview("계단 피하기")
    assert len(calls) == 1
    assert service.preview_status().available


def test_more_than_previous_maximum_calls_do_not_disable_preview(monkeypatch):
    clock = [100.0]
    calls = []
    monkeypatch.setattr(service, "monotonic", lambda: clock[0])
    def post(url, **kwargs):
        calls.append(kwargs["json"]["state"])
        return httpx.Response(200, request=httpx.Request("POST", url), json=_response(kwargs["json"]))
    monkeypatch.setattr(service.httpx, "post", post)
    for i in range(1005):
        service.analyze_preview(f"공개 모의 입력 {i}")
        clock[0] += 1
    assert len(calls) == 1005
    assert service.preview_status().available
    assert "remaining_calls" not in service.preview_status().model_dump()


def test_request_spacing_remains_without_a_cumulative_cap(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(200, request=httpx.Request("POST", url), json=_response(kwargs["json"]))
    monkeypatch.setattr(service.httpx, "post", post)
    service.analyze_preview("계단 없이")
    with pytest.raises(service.PreviewLimited):
        service.analyze_preview("CCTV 많은 길")
    assert len(calls) == 1
    monkeypatch.setattr(service, "monotonic", lambda: 101.0)
    service.analyze_preview("CCTV 많은 길")
    assert len(calls) == 2


def test_actual_cards_use_supported_metrics_and_time_policy_not_preview():
    selected = {"metrics": {"stairs_distance_m": 0, "streetlight_score": 77, "cctv_score": None},
                "route": {"properties": {"crossing_data_available": False, "pedestrian_bridge_count": 2}}}
    preferences = [RoutePreference(factor="stairs_distance_m", direction="avoid"),
                   RoutePreference(factor="streetlight_score", direction="maximize"),
                   RoutePreference(factor="cctv_score", direction="maximize")]
    from datetime import time
    arguments = SimpleNamespace(stairs_weight=0, crossing_weight=0, departure_time=time(22))
    cards = routing_condition_cards(selected, preferences, [], arguments, SimpleNamespace(is_night=True))
    states = {card.factor: card.state for card in cards}
    assert len(cards) == 8
    assert states["bridge"] == "not_applied"
    assert states["stairs"] == states["streetlight"] == states["time"] == "applied"
    assert states["safety"] == states["cctv"] == "not_applied"
    assert cards[-1].period == "night"
