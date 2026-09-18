import pytest

from app.services import local_llm_service
from app.services.local_llm_service import LocalLLMOutputError


def test_local_llm_parses_structured_route_intent(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {
            "message": {
                "content": """{
                    "departure_time": "22:00:00",
                    "profile": "pedestrian",
                    "preferences": [
                        {
                            "factor": "streetlight_score",
                            "direction": "maximize",
                            "weight": 1
                        }
                    ]
                }"""
            }
        }

    monkeypatch.setattr(local_llm_service, "_request_ollama", fake_request)

    intent = local_llm_service.parse_route_intent(
        "밤 10시에 가로등이 많은 길로 안내해줘"
    )

    assert str(intent.departure_time) == "22:00:00"
    assert intent.preferences[0].factor == "streetlight_score"
    assert captured["model"] == "qwen3:4b"
    assert captured["stream"] is False
    assert captured["think"] is False
    assert isinstance(captured["format"], dict)


def test_local_llm_rejects_non_schema_output(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": "not-json"}},
    )

    with pytest.raises(LocalLLMOutputError):
        local_llm_service.parse_route_intent("아무 길이나 찾아줘")


def test_local_llm_retries_semantically_invalid_time_factor(monkeypatch) -> None:
    responses = iter(
        [
            {
                "message": {
                    "content": """{
                        "departure_time": null,
                        "profile": "pedestrian",
                        "preferences": [
                            {"factor": "departure_time", "direction": "minimize", "weight": 1}
                        ]
                    }"""
                }
            },
            {
                "message": {
                    "content": """{
                        "departure_time": "22:00:00",
                        "profile": "pedestrian",
                        "preferences": []
                    }"""
                }
            },
        ]
    )
    calls: list[dict[str, object]] = []

    def fake_request(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload.copy())
        return next(responses)

    monkeypatch.setattr(local_llm_service, "_request_ollama", fake_request)

    intent = local_llm_service.parse_route_intent("밤 10시에 출발할래")

    assert str(intent.departure_time) == "22:00:00"
    assert len(calls) == 2
    assert len(calls[1]["messages"]) == 4


def test_local_llm_retries_when_explicit_time_is_omitted(monkeypatch) -> None:
    responses = iter(
        [
            {
                "message": {
                    "content": """{
                        "departure_time": null,
                        "profile": "pedestrian",
                        "preferences": [
                            {"factor": "streetlight_score", "direction": "maximize", "weight": 1}
                        ]
                    }"""
                }
            },
            {
                "message": {
                    "content": """{
                        "departure_time": "22:00:00",
                        "profile": "pedestrian",
                        "preferences": [
                            {"factor": "streetlight_score", "direction": "maximize", "weight": 1}
                        ]
                    }"""
                }
            },
        ]
    )
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: next(responses),
    )

    intent = local_llm_service.parse_route_intent(
        "밤 10시에 가로등이 많은 길로 안내해줘"
    )

    assert str(intent.departure_time) == "22:00:00"
