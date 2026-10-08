import json

import pytest

from app.services.incomplete_conditions import incomplete_condition_factors
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
