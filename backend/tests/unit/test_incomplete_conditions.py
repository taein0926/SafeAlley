import json
from pathlib import Path

import pytest

from app.services.incomplete_conditions import (
    has_explicit_safety_facility_request,
    incomplete_condition_factors,
    preview_factor_evidence,
)
from app.services import local_llm_service as llm
from app.services.jev_preview_service import build_request, parse_decisions


@pytest.mark.parametrize("query,expected", [
    ("CCTV가 많고 건널목을", {"crosswalk_count"}),
    ("건널목을.", {"crosswalk_count"}),
    ("계단을", {"stairs_distance_m"}),
    ("가로등이", {"streetlight_score"}),
    ("cctv는", {"cctv_score"}),
    ("계단과 건널목을", {"stairs_distance_m", "crosswalk_count"}),
    ("계단도 건널목도", {"stairs_distance_m", "crosswalk_count"}),
    ("계단과 건널목을 적게 지나는 길", set()),
    ("계단을 피하고 건널목을 적게", set()),
    ("계단 없이 가고 가로등이 많은 길", set()),
    ("건널목을 적게 지나는 길로. 건널목을", set()),
    ("주안역에서 인천사랑병원까지", set()),
])
def test_unfinished_noun_guard_is_not_a_general_parser(query, expected):
    assert incomplete_condition_factors(query) == expected


@pytest.mark.parametrize("query", [
    "안전시설과 가깝고 계단이 적은 길",
    "도움시설에 접근하기 좋은 길로 안내해줘",
    "가까운 안전시설을 우선해줘",
])
def test_explicit_safety_facility_request_is_detected(query):
    assert has_explicit_safety_facility_request(query)


@pytest.mark.parametrize("query", [
    "안전시설은 고려하지 않아도 돼",
    "안전시설은 상관없고 계단만 적은 길로 가줘",
    "도움시설은 빼고 가로등을 우선해줘",
])
def test_cancelled_safety_facility_request_is_not_detected(query):
    assert not has_explicit_safety_facility_request(query)


@pytest.mark.parametrize("query,factor,evidence,choice", [
    ("최단거리로 가고", "distance", "positive", "apply"),
    ("가로등이 많고", "streetlight", "positive", "apply"),
    ("CCTV가 많고", "cctv", "positive", "apply"),
    ("안전시설과 가깝고", "safety", "positive", "apply"),
    ("계단이 적고", "stairs", "positive", "minimize"),
    ("계단 없이", "stairs", "positive", "avoid"),
    ("건널목을 적게 건너고", "crossing", "positive", "minimize"),
    ("육교를 이용하고", "bridge", "positive", "apply"),
    ("육교를 피하고", "bridge", "positive", "avoid"),
    ("밤 10시에", "time", "positive", "night"),
    ("낮 2시에", "time", "positive", "day"),
    ("오후 10시에", "time", "positive", "night"),
    ("오전 2시에", "time", "positive", "night"),
    ("오전 10시에", "time", "positive", "day"),
    ("가로등이", "streetlight", "incomplete", "pending"),
    ("CCTV가", "cctv", "incomplete", "pending"),
    ("계단을", "stairs", "incomplete", "pending"),
    ("밤", "time", "incomplete", "pending"),
    ("계단은 피하지 않아도 되고", "stairs", "negative", "skip"),
    ("건널목은 건너도 괜찮고", "crossing", "negative", "skip"),
    ("CCTV는 상관없고", "cctv", "negative", "skip"),
    ("육교만 피하고", "stairs", "absent", None),
    ("도움시설 적고", "safety", "negative", "skip"),
    ("가로등 적고", "streetlight", "negative", "skip"),
    ("CCTV가 적고", "cctv", "negative", "skip"),
    ("계단 많고", "stairs", "negative", "skip"),
    ("건널목 많은 길", "crossing", "negative", "skip"),
])
def test_preview_factor_source_evidence(query, factor, evidence, choice):
    assert preview_factor_evidence(query, factor) == (evidence, choice)


def test_each_factor_uses_only_its_own_clause():
    query = "도움시설 적고 계단 많고 건널목 많은 길로 안내해"
    assert preview_factor_evidence(query, "safety") == ("negative", "skip")
    assert preview_factor_evidence(query, "stairs") == ("negative", "skip")
    assert preview_factor_evidence(query, "crossing") == ("negative", "skip")


@pytest.mark.parametrize("query,factor,evidence,choice", [
    ("아침에 육교 말고 건널목으로 안내해줘", "bridge", "positive", "avoid"),
    ("아침에 육교 말고 건널목으로 안내해줘", "crossing", "negative", "skip"),
    ("소방서 근처를 지나고 계단은 줄일 생각 없어", "safety", "positive", "apply"),
    ("소방서 근처를 지나고 계단은 줄일 생각 없어", "stairs", "negative", "skip"),
    ("최단거리보다는 환하고 씨씨티비가 많은 길로 가줘", "distance", "negative", "skip"),
    ("최단거리보다는 환하고 씨씨티비가 많은 길로 가줘", "streetlight", "positive", "apply"),
    ("최단거리보다는 환하고 씨씨티비가 많은 길로 가줘", "cctv", "positive", "apply"),
    ("안전시설보다 지름길이 좋아", "safety", "negative", "skip"),
    ("안전시설보다 지름길이 좋아", "distance", "positive", "apply"),
])
def test_compound_comparison_and_alternative_requests(query, factor, evidence, choice):
    assert preview_factor_evidence(query, factor) == (evidence, choice)


@pytest.mark.parametrize("query,factor,evidence,choice", [
    ("건널목은 안 줄일래", "crossing", "negative", "skip"),
    ("최단거리는 싫어", "distance", "negative", "skip"),
    ("지름길은 싫어", "distance", "negative", "skip"),
    ("최단거리 대신 밝은 길로 가줘", "distance", "negative", "skip"),
    ("최단거리 대신 밝은 길로 가줘", "streetlight", "positive", "apply"),
    ("최단거리보단 안전한 길이 좋아", "distance", "negative", "skip"),
    ("최단거리보단 안전한 길이 좋아", "safety", "positive", "apply"),
    ("병원을 지나가는 길로 가줘", "safety", "positive", "apply"),
    ("소방서 옆으로 가줘", "safety", "positive", "apply"),
    ("경찰서 인근으로 안내해줘", "safety", "positive", "apply"),
    ("응급실 옆을 지나가줘", "safety", "positive", "apply"),
    ("119안전센터를 경유해줘", "safety", "positive", "apply"),
    ("오늘 밤 출발할게", "time", "positive", "night"),
    ("새벽 출발로 해줘", "time", "positive", "night"),
    ("육교로 가줘", "bridge", "positive", "apply"),
    ("밝게 다닐 수 있는 길", "streetlight", "positive", "apply"),
    ("길이 밝고 환했으면 좋겠어", "streetlight", "positive", "apply"),
])
def test_additional_natural_language_variants(query, factor, evidence, choice):
    assert preview_factor_evidence(query, factor) == (evidence, choice)


@pytest.mark.parametrize("query,factor,evidence,choice", [
    ("가로등많은길로가줘", "streetlight", "positive", "apply"),
    ("계단안가는길로가줘", "stairs", "positive", "avoid"),
    ("씨씨티비 마는 길로 가줘", "cctv", "positive", "apply"),
    ("건널목 쫌 적게 가줘", "crossing", "positive", "minimize"),
    ("밤에안전한길루 안내해줘", "time", "positive", "night"),
    ("밤에안전한길루 안내해줘", "safety", "positive", "apply"),
    ("계단은 피하고 아니, 계단은 괜찮고 육교만 피할게", "stairs", "negative", "skip"),
    ("계단은 피하고 아니, 계단은 괜찮고 육교만 피할게", "bridge", "positive", "avoid"),
    ("가로등보다 CCTV가 좋아. 그냥 둘 다 많은 길로 가줘", "streetlight", "positive", "apply"),
    ("가로등보다 CCTV가 좋아. 그냥 둘 다 많은 길로 가줘", "cctv", "positive", "apply"),
    ("밤 10시가 아니라 오전 10시에 출발해", "time", "positive", "day"),
])
def test_typo_spacing_colloquial_and_late_corrections(query, factor, evidence, choice):
    assert preview_factor_evidence(query, factor) == (evidence, choice)


def test_qwen_invented_crossing_direction_is_removed_without_losing_cctv(monkeypatch):
    llm.clear_intent_cache()
    content = {"departure_time": "14:00:00", "preferences": [
        {"factor": "cctv_score", "direction": "maximize"},
        {"factor": "crosswalk_count", "direction": "minimize"}]}
    monkeypatch.setattr(llm, "_request_ollama", lambda _: {"message": {"content": json.dumps(content)}})
    intent = llm.parse_route_intent("낮 2시에 CCTV가 많고 건널목을")
    assert {p.factor for p in intent.preferences} == {"cctv_score"}


def test_jev_guess_for_incomplete_condition_stays_analyzing():
    payload = build_request("CCTV가 많고 건널목을", "test")
    answers = {key: {"type": "choice", "choice": "skip", "confidence": 1} for key in payload["questions"]}
    answers["cctv"]["choice"] = "apply"
    answers["crossing"]["choice"] = "minimize"
    cards = parse_decisions(payload, {"answers": answers}, .7)
    crossing = next(c for c in cards if c.factor == "crossing")
    assert crossing.state == "analyzing" and crossing.direction is None and crossing.judgment == "pending"
    assert next(c for c in cards if c.factor == "cctv").state == "applied"


def test_live_preview_language_regression_corpus():
    path = Path(__file__).parents[2] / "evals" / "live_intent_preview_regression_20261014.json"
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert len(cases) >= 25
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert preview_factor_evidence(case["query"], case["factor"]) == (
            case["evidence"], case.get("choice")
        ), case["id"]
