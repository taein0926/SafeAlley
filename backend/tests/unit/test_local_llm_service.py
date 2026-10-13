import json

import pytest

from app.schemas.agent import ParsedRouteIntent
from app.services import local_llm_service
from app.services.local_llm_service import LocalLLMOutputError


@pytest.fixture(autouse=True)
def isolated_intent_cache():
    local_llm_service.clear_intent_cache()
    yield
    local_llm_service.clear_intent_cache()


def test_cached_intents_are_isolated_and_queries_are_not_conflated(monkeypatch):
    calls = []
    def request(payload):
        calls.append(payload)
        return {"message": {"content": '{"preferences":[{"factor":"distance_m","direction":"minimize"}]}'}}
    monkeypatch.setattr(local_llm_service, "_request_ollama", request)
    first = local_llm_service.parse_route_intent("최단 길")
    first.preferences.clear()
    second = local_llm_service.parse_route_intent("  최단 길  ")
    assert len(second.preferences) == 1
    assert second.profile == "pedestrian"
    assert second.preferences[0].weight == 1
    assert len(calls) == 1
    local_llm_service.parse_route_intent("다른 길")
    assert len(calls) == 2
    assert calls[0]["keep_alive"] == "10m"


def test_intent_cache_expires_and_respects_model_and_disable(monkeypatch):
    from app.core.config import Settings
    settings = Settings(ollama_intent_cache_seconds=10)
    monkeypatch.setattr(local_llm_service, "get_settings", lambda: settings)
    clock = [0.0]
    monkeypatch.setattr(local_llm_service, "monotonic", lambda: clock[0])
    calls = []
    def request(payload):
        calls.append(payload)
        return {"message": {"content": '{}'}}
    monkeypatch.setattr(local_llm_service, "_request_ollama", request)
    local_llm_service.parse_route_intent("길 안내")
    local_llm_service.parse_route_intent("길 안내")
    assert len(calls) == 1
    clock[0] = 11
    local_llm_service.parse_route_intent("길 안내")
    assert len(calls) == 2
    settings.ollama_model = "another-model"
    local_llm_service.parse_route_intent("길 안내")
    assert len(calls) == 3
    settings.ollama_intent_cache_seconds = 0
    local_llm_service.parse_route_intent("길 안내")
    local_llm_service.parse_route_intent("길 안내")
    assert len(calls) == 5


def test_invalid_intent_is_not_cached(monkeypatch):
    calls = []
    def request(payload):
        calls.append(payload)
        return {"message": {"content": 'invalid'}}
    monkeypatch.setattr(local_llm_service, "_request_ollama", request)
    for _ in range(2):
        with pytest.raises(LocalLLMOutputError):
            local_llm_service.parse_route_intent("길 안내")
    assert len(calls) == 4


def test_intent_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(local_llm_service, "_INTENT_CACHE_MAX_SIZE", 2)
    monkeypatch.setattr(local_llm_service, "_request_ollama", lambda _: {"message": {"content": '{}'}})
    for query in ["a", "b", "c"]:
        local_llm_service.parse_route_intent(query)
    assert len(local_llm_service._intent_cache) == 2
    assert {key[-1] for key in local_llm_service._intent_cache} == {"b", "c"}


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
    assert captured["model"] == "gemma4:26b"
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


@pytest.mark.parametrize(
    ("query", "model_time", "expected_time"),
    [
        (
            "오전 8시가 아니라 오전 9시 15분에 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "08:00:00",
            "09:15:00",
        ),
        (
            "밤 10시 말고 밤 11시에 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "22:00:00",
            "23:00:00",
        ),
        (
            "오후 2시까지 도착해야 해. 오전 8시에 도화역에서 수봉공원까지 출발할래",
            "14:00:00",
            "08:00:00",
        ),
        (
            "오후 2시에 도착할 거야. 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "14:00:00",
            None,
        ),
        (
            "오전 8시에 출발하려다 9시로 바꿨어. 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "09:00:00",
            "09:00:00",
        ),
        (
            "밤 10시에 출발할까 했는데 밤 11시로 바꿨어. 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "22:00:00",
            "23:00:00",
        ),
        (
            "오후 2시에 도착하려 했는데 오후 3시로 바꿨어. 도화역에서 수봉공원까지 계단 없는 길로 가줘",
            "15:00:00",
            None,
        ),
    ],
)
def test_departure_time_correction_does_not_use_arrival_time(
    monkeypatch, query, model_time, expected_time
) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "도화역",
            "destination_name": "수봉공원",
            "departure_time": model_time,
            "preferences": [{"factor": "stairs_distance_m", "direction": "avoid"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert (intent.departure_time.isoformat() if intent.departure_time else None) == expected_time
    assert intent.origin_name == "도화역"
    assert intent.destination_name == "수봉공원"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "오후 2시까지 도착해야 해. 오전 8시에 도화역에서 수봉공원까지 출발할래",
            {},
        ),
        (
            "오후 2시까지 도착해야 해. 오전 8시에 도화역에서 수봉공원까지 짧은 길로 출발할래",
            {"distance_m": "minimize"},
        ),
    ],
)
def test_arrival_deadline_does_not_invent_shortest_route(monkeypatch, query, expected) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "도화역",
            "destination_name": "수봉공원",
            "departure_time": "14:00:00",
            "preferences": [{"factor": "distance_m", "direction": "minimize"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert intent.departure_time.isoformat() == "08:00:00"
    assert {item.factor: item.direction for item in intent.preferences} == expected


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


@pytest.mark.parametrize(
    ("query", "model_preferences", "expected"),
    [
        (
            "주안역에서 수봉공원까지 가로등 많은 길로. 아니 가로등 말고 CCTV 많은 길로",
            {"streetlight_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "도화역에서 인천사랑병원까지 계단을 피해줘. 정정할게, 계단은 상관없고 보도를 많이 지나는 길로",
            {"stairs_distance_m": "avoid"},
            {"sidewalk_coverage_percent": "maximize"},
        ),
        (
            "수봉공원에서 주안역까지 CCTV 많은 길로. 아니 CCTV는 빼고 계단만 피하고 싶어",
            {"cctv_score": "maximize", "stairs_distance_m": "avoid"},
            {"stairs_distance_m": "avoid"},
        ),
        (
            "도화역에서 주안역까지 횡단보도 없는 길로. 다시 말하면 없는 건 아니고 적게 건너면 돼",
            {"crosswalk_count": "avoid"},
            {"crosswalk_count": "minimize"},
        ),
    ],
)
def test_final_explicit_correction_replaces_superseded_preferences(
    monkeypatch, query, model_preferences, expected
) -> None:
    model_output = {
        "origin_name": query.split("에서", 1)[0],
        "destination_name": query.split("에서", 1)[1].split("까지", 1)[0],
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in model_preferences.items()
        ],
    }
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps(model_output, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert {item.factor: item.direction for item in intent.preferences} == expected


def test_arrival_deadline_with_place_between_clock_and_arrival_is_not_departure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "인천사랑병원",
            "departure_time": "09:00:00",
            "preferences": [{"factor": "distance_m", "direction": "minimize"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "오전 9시까지 인천사랑병원에 도착하고 싶어. 주안역에서 출발할게"
    )

    assert intent.departure_time is None
    assert intent.preferences == []


def test_excluding_stairs_from_route_is_not_discarding_the_stairs_preference(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "수봉공원",
            "preferences": [
                {"factor": "crosswalk_count", "direction": "minimize"},
                {"factor": "streetlight_score", "direction": "maximize"},
            ],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "밤에 주안역에서 수봉공원까지 계단은 빼고 횡단보도도 적게 건너면서 가로등 많은 길로"
    )

    assert {item.factor: item.direction for item in intent.preferences} == {
        "stairs_distance_m": "avoid",
        "crosswalk_count": "minimize",
        "streetlight_score": "maximize",
    }


@pytest.mark.parametrize(
    ("query", "model_preferences", "expected"),
    [
        (
            "주안역에서 수봉도서관까지 계단은 몇 개 있어도 괜찮아. CCTV가 많은 쪽으로 가줘",
            {"stairs_count": "minimize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "주안역에서 인천사랑병원까지 계단을 피하려고 했는데 생각이 바뀌었어. 계단은 상관없고 CCTV가 많은 길로",
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "현대유비스병원에서 도화역까지 건널목 없는 길로. 정확히는 건널목이 적으면 돼",
            {"crosswalk_count": "avoid"},
            {"crosswalk_count": "minimize"},
        ),
    ],
)
def test_last_user_intent_overrides_earlier_or_permissive_factor(
    monkeypatch, query, model_preferences, expected
) -> None:
    model_output = {
        "origin_name": query.split("에서", 1)[0],
        "destination_name": query.split("에서", 1)[1].split("까지", 1)[0],
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in model_preferences.items()
        ],
    }
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps(model_output, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "model_preferences", "expected"),
    [
        (
            "주안역에서 인천사랑병원까지 계단은 피하지 말고 최단거리로 가줘",
            {"stairs_distance_m": "avoid", "distance_m": "minimize"},
            {"distance_m": "minimize"},
        ),
        (
            "주안역에서 인천사랑병원까지 횡단보도는 피하지 말고 계단만 피해줘",
            {"crosswalk_count": "minimize", "stairs_distance_m": "avoid"},
            {"stairs_distance_m": "avoid"},
        ),
        (
            "주안역에서 인천사랑병원까지 평지는 필요 없고 CCTV 많은 길로 가줘",
            {"max_slope_percent": "minimize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "주안역에서 인천사랑병원까지 짧은 길보다는 CCTV가 많은 길이 좋아",
            {"distance_m": "minimize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "수봉도서관에서 수봉공원까지 계단 없는 게 더 중요해. 좀 멀어져도 괜찮아",
            {"stairs_distance_m": "avoid", "distance_m": "minimize"},
            {"stairs_distance_m": "avoid"},
        ),
        (
            "주안역에서 인천사랑병원까지 계단은 피할 필요 없고 CCTV가 많은 길이면 돼",
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "도화역에서 수봉공원까지 엘리베이터가 있는 길로 가고 싶어",
            {"elevator_distance_m": "minimize"},
            {"elevator_accessibility": "maximize"},
        ),
        (
            "주안역에서 인천사랑병원까지 사람이 덜 붐비는 길로 가줘",
            {"traffic_congestion": "minimize"},
            {"crowd_density": "minimize"},
        ),
        (
            "주안역에서 인천사랑병원까지 어두운 길을 피하고 계단 없이 가줘",
            {"streetlight_score": "avoid"},
            {"streetlight_score": "maximize", "stairs_distance_m": "avoid"},
        ),
        (
            "주안역에서 인천사랑병원까지 CCTV 많은 길로 가되 너무 멀리 돌아가지 않게 해줘",
            {"cctv_score": "maximize"},
            {"cctv_score": "maximize", "distance_m": "minimize"},
        ),
    ],
)
def test_semantic_reconciliation_does_not_reverse_user_request(
    monkeypatch, query, model_preferences, expected
) -> None:
    model_output = {
        "origin_name": query.split("에서", 1)[0],
        "destination_name": query.split("에서", 1)[1].split("까지", 1)[0],
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in model_preferences.items()
        ],
    }
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps(model_output, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert {item.factor: item.direction for item in intent.preferences} == expected


def test_pm_half_hour_is_corrected_without_dropping_stairs(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "인천사랑병원",
            "departure_time": "22:00:00",
            "preferences": [],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "밤 10시 반에 주안역에서 인천사랑병원까지 계단 없이 가줘"
    )

    assert str(intent.departure_time) == "22:30:00"
    assert {item.factor: item.direction for item in intent.preferences} == {
        "stairs_distance_m": "avoid"
    }


def test_unmentioned_origin_is_not_sent_to_place_resolver(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "인천사랑병원",
            "preferences": [{"factor": "cctv_score", "direction": "maximize"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "인천사랑병원까지 CCTV가 많은 길로 가고 싶어"
    )

    assert intent.origin_name is None
    assert intent.destination_name == "인천사랑병원"


def test_am_twelve_means_midnight(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "더나눔병원",
            "departure_time": "12:00:00",
            "preferences": [{"factor": "safety_score", "direction": "maximize"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "오전 12시에 주안역에서 더나눔병원까지 안전한 길로 가줘"
    )

    assert str(intent.departure_time) == "00:00:00"


def test_one_sided_destination_recovers_the_literal_name(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": None,
            "destination_name": "까지",
            "preferences": [{"factor": "stairs_distance_m", "direction": "avoid"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "도화초등학교까지 계단 없는 길로 안내해줘"
    )

    assert intent.origin_name is None
    assert intent.destination_name == "도화초등학교"


@pytest.mark.parametrize(
    ("query", "model_preferences", "expected"),
    [
        (
            "수봉공원에서 도화역까지 횡단보도는 건너도 괜찮아. CCTV가 많은 쪽으로 가줘",
            {"crosswalk_count": "minimize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "도화역에서 수봉도서관까지 평지가 아니어도 돼. 가로등이 많은 길로 가줘",
            {"max_slope_percent": "minimize", "streetlight_score": "maximize"},
            {"streetlight_score": "maximize"},
        ),
        (
            "도화역에서 수봉공원까지 유모차가 다닐 수 있는 길로 가줘",
            {"wheelchair_accessibility": "maximize"},
            {"stroller_accessibility": "maximize"},
        ),
    ],
)
def test_permissive_or_unmet_need_is_not_substituted(
    monkeypatch, query, model_preferences, expected
) -> None:
    model_output = {
        "origin_name": query.split("에서", 1)[0],
        "destination_name": query.split("에서", 1)[1].split("까지", 1)[0],
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in model_preferences.items()
        ],
    }
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps(model_output, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "model_preferences", "expected"),
    [
        (
            "더나눔병원에서 인천사랑병원까지 계단이 적고 보도가 많은 경로가 좋아",
            {"stairs_count": "minimize", "sidewalk_coverage_percent": "maximize"},
            {"stairs_distance_m": "minimize", "sidewalk_coverage_percent": "maximize"},
        ),
        (
            "주안역에서 인천사랑병원까지 계단이 있어도 괜찮으니 가까운 길로 안내해줘",
            {"distance_m": "minimize"},
            {"distance_m": "minimize"},
        ),
        (
            "도화역에서 수봉도서관까지 가장 짧은 길보단 보도가 많은 길을 골라줘",
            {"distance_m": "minimize", "sidewalk_coverage_percent": "maximize"},
            {"sidewalk_coverage_percent": "maximize"},
        ),
        (
            "인천사랑병원에서 현대유비스병원까지 평지 위주로 가되 경찰서 가까운 길을 추천해줘",
            {"max_slope_percent": "minimize", "police_accessibility": "maximize", "distance_m": "minimize"},
            {"max_slope_percent": "minimize", "police_accessibility": "maximize"},
        ),
    ],
)
def test_explicit_supported_route_preferences_use_router_factors(
    monkeypatch, query, model_preferences, expected
) -> None:
    model_output = {
        "origin_name": query.split("에서", 1)[0],
        "destination_name": query.split("에서", 1)[1].split("까지", 1)[0],
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in model_preferences.items()
        ],
    }
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps(model_output, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(query)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "candidate", "expected"),
    [
        (
            "계단은 좀 있어도 돼. CCTV가 많은 길로 가줘",
            {"stairs_distance_m": "minimize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "횡단보도를 건너도 상관없으니 가로등 많은 길로 가줘",
            {"crosswalk_count": "minimize", "streetlight_score": "maximize"},
            {"streetlight_score": "maximize"},
        ),
        (
            "가로등이 적어도 괜찮으니 빠른 길로 가줘",
            {"streetlight_score": "maximize", "distance_m": "minimize"},
            {"distance_m": "minimize"},
        ),
        (
            "가까운 길보다 계단을 피하는 길이 좋아",
            {"distance_m": "minimize", "stairs_distance_m": "avoid"},
            {"stairs_distance_m": "avoid"},
        ),
        (
            "횡단보도가 적은 길보다는 가로등이 많은 길로 가줘",
            {"crosswalk_count": "minimize", "streetlight_score": "maximize"},
            {"streetlight_score": "maximize"},
        ),
        (
            "횡단보도는 가급적 적고 보도가 많은 길로 가줘",
            {"crosswalk_count": "minimize", "sidewalk_coverage_percent": "maximize"},
            {"crosswalk_count": "minimize", "sidewalk_coverage_percent": "maximize"},
        ),
        (
            "계단 없는 길과 CCTV 많은 길 둘 다 중요해",
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
        ),
    ],
)
def test_explicit_nonrequest_guard_preserves_actual_requests(query, candidate, expected) -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in candidate.items()
        ]
    })

    local_llm_service._prune_explicit_nonrequests(query, intent)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "candidate", "expected"),
    [
        (
            "경찰서 가까운 길보다 짧은 길",
            {"police_accessibility": "avoid", "distance_m": "minimize"},
            {"distance_m": "minimize"},
        ),
        (
            "가로등 많은 길보다 CCTV 많은 길",
            {"streetlight_score": "maximize", "cctv_score": "maximize"},
            {"cctv_score": "maximize"},
        ),
        (
            "계단 적은 길보다 밝은 길",
            {"stairs_distance_m": "minimize", "streetlight_score": "maximize"},
            {"streetlight_score": "maximize"},
        ),
        (
            "CCTV 많은 길보다 계단 없는 길이 좋지만 CCTV도 많으면 좋겠어",
            {"cctv_score": "maximize", "stairs_distance_m": "avoid"},
            {"cctv_score": "maximize", "stairs_distance_m": "avoid"},
        ),
        (
            "CCTV 많은 길도 중요해. 경찰서 가까운 길보다 짧은 길",
            {"cctv_score": "maximize", "police_accessibility": "minimize", "distance_m": "minimize"},
            {"cctv_score": "maximize", "distance_m": "minimize"},
        ),
        (
            "계단 없고 CCTV 많은 길",
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
            {"stairs_distance_m": "avoid", "cctv_score": "maximize"},
        ),
    ],
)
def test_comparison_antecedent_guard_keeps_chosen_conditions(query, candidate, expected) -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [
            {"factor": factor, "direction": direction}
            for factor, direction in candidate.items()
        ]
    })

    local_llm_service._prune_comparison_antecedents(query, intent)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("CCTV 많은 길로 가줘. 아니, CCTV는 필요 없어", {}),
        ("CCTV는 필요 없어. 아니, CCTV 많은 길로 가줘", {"cctv_score": "maximize"}),
        ("CCTV 많은 길로 가줘. CCTV도 많으면 좋겠어", {"cctv_score": "maximize"}),
        ("가로등 많은 길이 좋아. 하지만 가로등은 중요하지 않아", {}),
    ],
)
def test_latest_explicit_factor_statement_governs_cancellation(query, expected) -> None:
    factor = "streetlight_score" if "가로등" in query else "cctv_score"
    intent = ParsedRouteIntent.model_validate({
        "preferences": [{"factor": factor, "direction": "maximize"}]
    })

    local_llm_service._prune_explicit_nonrequests(query, intent)

    assert {item.factor: item.direction for item in intent.preferences} == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("경찰서 가까운 길보다 짧은 길로 가줘", {"distance_m": "minimize"}),
        ("경찰서 가까운 길보다 짧고 인도가 많은 길로 가줘", {"distance_m": "minimize"}),
        ("CCTV가 많은 길이 좋아. 경찰서 가까운 길보다 짧은 길도 원해", {"distance_m": "minimize"}),
        ("새벽 5시 15분에 주안역에서 더나눔병원까지 빠르게 가줘", {"distance_m": "minimize"}),
        ("주안역에서 인천사랑병원까지 빨리 안내해줘", {"distance_m": "minimize"}),
        ("주안역에서 인천사랑병원까지 빠르게 갈 필요는 없어", {}),
        ("주안역에서 인천사랑병원까지 빨리 가지 않아도 돼", {}),
        ("짧은 길보다는 CCTV가 많은 길로 가줘", {}),
        ("최단거리 말고 계단 없는 길로 가줘", {}),
        ("경찰서 가까운 길로 가줘", {}),
        ("계단이 짧고 CCTV가 많은 길로 가줘", {}),
        ("짧은 길은 필요 없어", {}),
    ],
)
def test_explicit_short_route_guard_only_recovers_requested_distance(query, expected) -> None:
    intent = ParsedRouteIntent.model_validate({"preferences": []})

    local_llm_service._preserve_explicit_short_route(query, intent)
    local_llm_service._prune_explicit_nonrequests(query, intent)
    local_llm_service._prune_comparison_antecedents(query, intent)

    assert {item.factor: item.direction for item in intent.preferences} == expected


def test_brightness_cancellation_in_later_sentence() -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [
            {"factor": "streetlight_score", "direction": "maximize"},
            {"factor": "distance_m", "direction": "minimize"},
        ]
    })

    local_llm_service._prune_explicit_nonrequests(
        "밝은 길로 가고 싶어. 아니, 밝기는 상관없고 짧은 길이면 돼", intent,
    )

    assert {item.factor for item in intent.preferences} == {"distance_m"}


@pytest.mark.parametrize(
    ("query", "factor"),
    [
        ("계단 한두 군데는 지나가도 괜찮아", "stairs_distance_m"),
        ("조명은 따지지 않을게", "streetlight_score"),
        ("건널목은 거쳐도 돼", "crosswalk_count"),
        ("CCTV는 많든 적든 괜찮고", "cctv_score"),
        ("계단은 있어도 무방해", "stairs_distance_m"),
    ],
)
def test_allowance_or_noncriterion_drops_unrequested_preference(query, factor) -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [{"factor": factor, "direction": "minimize"}]
    })

    local_llm_service._prune_explicit_nonrequests(query, intent)

    assert intent.preferences == []


def test_correction_without_repeated_factor_uses_last_named_factor() -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [{"factor": "crosswalk_count", "direction": "avoid"}]
    })

    local_llm_service._apply_explicit_correction(
        "건널목은 빼고 가줘. 정확히는 조금 적게 건너면 돼", intent,
    )

    assert [(item.factor, item.direction) for item in intent.preferences] == [
        ("crosswalk_count", "minimize")
    ]


def test_reconsidered_crossing_and_gentle_slope_use_requested_directions() -> None:
    crossing = ParsedRouteIntent.model_validate({
        "preferences": [{"factor": "crosswalk_count", "direction": "avoid"}]
    })
    local_llm_service._apply_explicit_correction(
        "횡단보도가 없는 길로. 다시 생각해보니 적게 건너면 돼", crossing,
    )
    assert crossing.preferences[0].direction == "minimize"

    slope = ParsedRouteIntent.model_validate({
        "preferences": [{"factor": "max_slope_percent", "direction": "maximize"}]
    })
    local_llm_service._normalize_explicit_route_preferences(
        "경사가 완만했으면 해", slope,
    )
    assert slope.preferences[0].direction == "minimize"


def test_reconsidered_crossing_allowance_cancels_earlier_avoidance() -> None:
    intent = ParsedRouteIntent.model_validate({
        "preferences": [
            {"factor": "crosswalk_count", "direction": "minimize"},
            {"factor": "streetlight_score", "direction": "maximize"},
        ]
    })

    local_llm_service._apply_explicit_correction(
        "건널목을 피하고 싶어. 생각이 바뀌었어. 몇 번은 건너도 돼. "
        "대신 가로등 많은 길로 가줘",
        intent,
    )

    assert {item.factor: item.direction for item in intent.preferences} == {
        "streetlight_score": "maximize",
    }


def test_vague_night_does_not_become_an_invented_hour(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "주안역",
            "destination_name": "인천사랑병원",
            "departure_time": "22:00:00",
            "preferences": [{"factor": "cctv_score", "direction": "maximize"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "밤에 주안역에서 인천사랑병원까지 CCTV 많은 길로 가줘"
    )

    assert intent.departure_time is None


def test_unset_origin_is_not_treated_as_a_place_name(monkeypatch) -> None:
    monkeypatch.setattr(
        local_llm_service,
        "_request_ollama",
        lambda _: {"message": {"content": json.dumps({
            "origin_name": "출발지",
            "destination_name": "현대유비스병원",
            "preferences": [{"factor": "stairs_distance_m", "direction": "avoid"}],
        }, ensure_ascii=False)}},
    )

    intent = local_llm_service.parse_route_intent(
        "현대유비스병원까지 계단 없는 길로 가고 싶어. 출발지는 아직 정하지 않았어"
    )

    assert intent.origin_name is None
    assert intent.destination_name == "현대유비스병원"


@pytest.mark.parametrize("model_destination", [None, "인천사랑병원으로"])
def test_one_sided_motion_destination_keeps_literal_place(model_destination) -> None:
    intent = ParsedRouteIntent.model_validate({
        "origin_name": None,
        "destination_name": model_destination,
        "preferences": [{"factor": "stairs_distance_m", "direction": "avoid"}],
    })

    local_llm_service._preserve_mentioned_places(
        "인천사랑병원으로 갈 건데 계단을 피해줘", intent,
    )

    assert intent.origin_name is None
    assert intent.destination_name == "인천사랑병원"
