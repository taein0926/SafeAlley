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


def test_local_llm_corrects_one_explicit_pm_hour_without_dropping_preferences(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": """{
            "origin_name":"주안역",
            "destination_name":"인천사랑병원",
            "departure_time":"10:00:00",
            "profile":"pedestrian",
            "preferences":[
                {"factor":"stairs_distance_m","direction":"avoid","weight":1},
                {"factor":"streetlight_score","direction":"maximize","weight":1},
                {"factor":"cctv_score","direction":"maximize","weight":1}
            ]
        }"""}},
    )

    intent = local_llm_service.parse_route_intent(
        "밤 10시에 주안역에서 인천사랑병원까지 계단 없이 가로등과 CCTV가 많은 길로 안내해줘"
    )

    assert str(intent.departure_time) == "22:00:00"
    assert {item.factor for item in intent.preferences} == {
        "stairs_distance_m", "streetlight_score", "cctv_score"
    }


def test_local_llm_preserves_explicit_no_stairs_when_model_omits_it(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": """{
            "origin_name":"주안역",
            "destination_name":"인천사랑병원",
            "departure_time":"10:00:00",
            "profile":"pedestrian",
            "preferences":[
                {"factor":"streetlight_score","direction":"maximize","weight":1},
                {"factor":"cctv_score","direction":"maximize","weight":1}
            ]
        }"""}},
    )

    intent = local_llm_service.parse_route_intent(
        "밤 10시에 주안역에서 인천사랑병원까지 계단 없이 가로등과 CCTV가 많은 길로 안내해줘"
    )

    assert str(intent.departure_time) == "22:00:00"
    assert {item.factor: item.direction for item in intent.preferences} == {
        "stairs_distance_m": "avoid",
        "streetlight_score": "maximize",
        "cctv_score": "maximize",
    }


def test_local_llm_preserves_explicit_flat_ground_when_model_omits_it(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": """{
            "origin_name":"주안역", "destination_name":"현대유비스병원",
            "departure_time":null, "profile":"pedestrian",
            "preferences":[{"factor":"cctv_score","direction":"maximize","weight":1}]
        }"""}},
    )

    intent = local_llm_service.parse_route_intent(
        "주안역에서 현대유비스병원까지 평지는 우선하고 CCTV가 많은 길로 찾아줘"
    )

    assert {item.factor: item.direction for item in intent.preferences} == {
        "max_slope_percent": "minimize", "cctv_score": "maximize"
    }


def test_local_llm_retries_flatness_alias_and_omitted_cctv(monkeypatch) -> None:
    responses = iter([
        {"message": {"content": """{
            "origin_name":"주안역", "destination_name":"현대유비스병원",
            "departure_time":null, "profile":"pedestrian",
            "preferences":[{"factor":"flatness","direction":"maximize","weight":1}]
        }"""}},
        {"message": {"content": """{
            "origin_name":"주안역", "destination_name":"현대유비스병원",
            "departure_time":null, "profile":"pedestrian",
            "preferences":[
                {"factor":"max_slope_percent","direction":"minimize","weight":1},
                {"factor":"cctv_score","direction":"maximize","weight":1}
            ]
        }"""}},
    ])
    monkeypatch.setattr(local_llm_service, "_request_ollama", lambda _: next(responses))

    intent = local_llm_service.parse_route_intent(
        "주안역에서 현대유비스병원까지 평지는 우선하고 CCTV가 많은 길을 찾아줘"
    )

    assert {item.factor: item.direction for item in intent.preferences} == {
        "max_slope_percent": "minimize", "cctv_score": "maximize"
    }
