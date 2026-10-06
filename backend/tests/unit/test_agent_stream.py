import json

from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import app
from app.schemas.agent import AgentExecutionResponse, ParsedRouteIntent


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
