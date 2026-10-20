"""Keep current offline evaluation data aligned without model or DB access."""
import json

from evals.evaluate_intent import CASE_SETS
from evals.evaluate_recommendation_explanations import CASES_PATH, _evaluate_case


def test_intent_sets_do_not_expect_retired_slope_preferences():
    files = {path for paths in CASE_SETS.values() for path in paths}
    assert files
    for path in files:
        for case in json.loads(path.read_text(encoding="utf-8")):
            assert not {"max_slope_percent", "flatness"}.intersection(case["preferences"]), (path.name, case)


def test_all_current_explanation_cases_pass_without_live_services():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 8
    for case in cases:
        assert {c["route_type"] for c in case["candidates"]} <= {"shortest", "custom"}
        assert not {"max_slope_percent", "intersection_distance_m"}.intersection(
            p["factor"] for p in case["preferences"])
        assert _evaluate_case(case), case["name"]
