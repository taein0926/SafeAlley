import json

from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import app
from app.schemas.agent import AgentExecutionResponse, ParsedRouteIntent
from app.repositories.place_repository import PlaceAmbiguousError


def test_stream_and_regular_query_share_the_same_workflow(monkeypatch):
    monkeypatch.setattr(agent_api, "parse_route_intent", lambda _: ParsedRouteIntent(
        origin_name="주안역", destination_name="인천사랑병원",
        preferences=[{"factor": "cctv_score", "direction": "maximize", "weight": 1}],
    ))
    monkeypatch.setattr(agent_api, "resolve_place", lambda name: {
        "name": name, "category": None, "address": None, "source": "test",
        "latitude": 37.46, "longitude": 126.68,
    })
    def execute(call, **kwargs):
        assert call.arguments.preference_mode == "explicit_only"
        return AgentExecutionResponse(
            tool_call=call, selected_route_type=None, selected_route=None,
            recommendation_status="no_supported_preferences", candidates=[], unsupported_preferences=[],
        )
    monkeypatch.setattr(agent_api, "execute_agent_tool", execute)
    monkeypatch.setattr(agent_api, "_execute_agent_tool", execute)
    client = TestClient(app)
    request = {"query": "주안역에서 인천사랑병원까지 CCTV 많은 길"}
    regular = client.post("/api/agent/query", json=request)
    streamed = client.post("/api/agent/query/stream", json=request)
    events = [json.loads(line) for line in streamed.text.splitlines()]

    assert regular.status_code == streamed.status_code == 200
    assert [event["type"] for event in events] == [
        "stage", "interpreted", "stage", "resolved", "stage", "result",
    ]
    assert [event["stage"] for event in events if event["type"] == "stage"] == [
        "interpreting", "resolving", "routing",
    ]
    assert events[-1]["data"] == regular.json()


def test_stream_reports_parser_error_without_claiming_route_completion(monkeypatch):
    from app.services.local_llm_service import LocalLLMOutputError

    def fail(_: str):
        raise LocalLLMOutputError("invalid local model output")

    monkeypatch.setattr(agent_api, "parse_route_intent", fail)
    response = TestClient(app).post("/api/agent/query/stream", json={"query": "경로 알려줘"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events == [
        {"type": "stage", "stage": "interpreting"},
        {"type": "error", "detail": "invalid local model output"},
    ]


def test_stream_identifies_which_apartment_endpoint_needs_map_selection(monkeypatch):
    monkeypatch.setattr(agent_api, "parse_route_intent", lambda _: ParsedRouteIntent(
        origin_name="테스트아파트", destination_name="서화초등학교",
    ))
    context = {
        "code": "building_selection_required",
        "place_name": "테스트아파트",
        "focus": {"west": 126.65, "south": 37.45, "east": 126.66, "north": 37.46},
    }
    monkeypatch.setattr(agent_api, "resolve_place", lambda _: (_ for _ in ()).throw(
        PlaceAmbiguousError("동을 선택해 주세요.", selection_context=context)
    ))
    response = TestClient(app).post("/api/agent/query/stream", json={"query": "아파트에서 학교까지"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1] == {
        "type": "error",
        "detail": {"message": "동을 선택해 주세요.", "target": "origin", **context},
    }


def test_ambiguous_destination_stops_routing_and_returns_campus_choices(monkeypatch):
    monkeypatch.setattr(agent_api, "parse_route_intent", lambda _: ParsedRouteIntent(
        origin_name="서화초", destination_name="인천대", departure_time="20:00:00",
        preferences=[{"factor": "stairs_distance_m", "direction": "avoid"}],
    ))
    candidates = [
        {"name": "인천대학교", "category": "building", "address": address, "source": "molit-gis-building", "latitude": 37.47, "longitude": 126.66}
        for address in ("도화동 995", "도화동 112-19")
    ]
    def resolve(name):
        if name == "인천대":
            raise PlaceAmbiguousError("선택해 주세요.", selection_context={
                "code": "place_selection_required", "place_name": name, "candidates": candidates,
            })
        return {**candidates[0], "name": "서화초등학교"}
    monkeypatch.setattr(agent_api, "resolve_place", resolve)
    def no_routing(*args, **kwargs):
        raise AssertionError("Do not route until the user selects a campus")
    monkeypatch.setattr(agent_api, "_execute_agent_tool", no_routing)
    response = TestClient(app).post("/api/agent/query/stream", json={"query": "서화초에서 인천대까지 계단을 피해 밤 8시에"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["detail"]["target"] == "destination"
    assert events[-1]["detail"]["candidates"] == candidates
    assert all(event.get("stage") != "routing" for event in events)


def test_selected_coordinates_keep_original_ai_preferences(monkeypatch):
    interpretation = ParsedRouteIntent(origin_name="서화초", destination_name="인천대", departure_time="20:00:00",
        preferences=[{"factor": "streetlight_score", "direction": "maximize"},
                     {"factor": "cctv_score", "direction": "maximize"},
                     {"factor": "stairs_distance_m", "direction": "avoid"}])
    monkeypatch.setattr(agent_api, "parse_route_intent", lambda _: interpretation)
    monkeypatch.setattr(agent_api, "resolve_place", lambda _: (_ for _ in ()).throw(AssertionError("Selected endpoints must not be resolved again")))
    def execute(call):
        assert call.arguments.departure_time.hour == 20
        assert call.arguments.destination.longitude == 126.66
        assert {item.factor: item.direction for item in call.arguments.preferences} == {
            "streetlight_score": "maximize", "cctv_score": "maximize", "stairs_distance_m": "avoid",
        }
        return AgentExecutionResponse(tool_call=call, selected_route_type=None, selected_route=None,
            recommendation_status="no_supported_preferences", candidates=[], unsupported_preferences=[])
    monkeypatch.setattr(agent_api, "execute_agent_tool", execute)
    response = TestClient(app).post("/api/agent/query", json={"query": "서화초에서 인천대까지 가로등 많고 cctv 많은 길로 안내해. 계단은 피했으면 하고 밤 8시에 갈거야.",
        "origin": {"latitude": 37.46, "longitude": 126.67}, "destination": {"latitude": 37.47, "longitude": 126.66}})
    assert response.status_code == 200
