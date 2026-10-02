import json

from app.schemas.agent import ParsedRouteIntent
from evals.evaluate_intent import CASE_SETS, _percentile, score_case


def test_score_case_separates_hard_avoid_false_positive() -> None:
    case = {
        "origin": "주안역",
        "destination": "인천사랑병원",
        "preferences": {"distance_m": "minimize"},
    }
    actual = ParsedRouteIntent.model_validate({
        "origin_name": "주안역",
        "destination_name": "인천사랑병원",
        "preferences": [{"factor": "stairs_distance_m", "direction": "avoid"}],
    })

    result = score_case(case, actual)

    assert result["hard_false_positive"] is True
    assert result["hard_false_negative"] is False
    assert result["unrequested_factors"] == ["stairs_distance_m"]
    assert result["missing_factors"] == ["distance_m"]
    assert result["checks"]["origin"] is True
    assert result["checks"]["preferences"] is False


def test_score_case_separates_hard_avoid_false_negative() -> None:
    case = {
        "origin": "주안역",
        "destination": "인천사랑병원",
        "preferences": {"stairs_distance_m": "avoid"},
    }
    actual = ParsedRouteIntent.model_validate({
        "origin_name": "주안역",
        "destination_name": "인천사랑병원",
        "preferences": [{"factor": "stairs_distance_m", "direction": "minimize"}],
    })

    result = score_case(case, actual)

    assert result["hard_false_positive"] is False
    assert result["hard_false_negative"] is True
    assert result["unrequested_factors"] == []
    assert result["wrong_direction_factors"] == ["stairs_distance_m"]


def test_new_holdout_is_separate_from_development_cases() -> None:
    dev_cases = [
        case
        for path in CASE_SETS["dev"]
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]
    holdout_cases = [
        case
        for path in CASE_SETS["holdout"]
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]

    assert len(dev_cases) == 50
    assert len(holdout_cases) == 12
    assert {case["query"] for case in dev_cases}.isdisjoint(
        {case["query"] for case in holdout_cases}
    )
    assert len({case["id"] for case in holdout_cases}) == len(holdout_cases)


def test_percentile_uses_observed_duration() -> None:
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert _percentile([], 0.95) is None


def test_prospective_cases_are_distinct_and_not_in_historical_suites() -> None:
    prospective_paths = (
        *CASE_SETS["prospective_probe_20261002"],
        *CASE_SETS["prospective_reserve_20261002"],
        *CASE_SETS["prospective_validation_20261002"],
        *CASE_SETS["prospective_final_20261002"],
    )
    prospective = [
        case for path in prospective_paths
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]
    historical = [
        case for paths in (CASE_SETS["dev"], CASE_SETS["regression"], CASE_SETS["holdout"])
        for path in paths
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]

    assert len(prospective) == 100
    assert len({case["id"] for case in prospective}) == 100
    assert len({case["query"] for case in prospective}) == 100
    assert {case["query"] for case in prospective}.isdisjoint(
        {case["query"] for case in historical}
    )
    assert all(
        {"id", "category", "query", "origin", "destination", "preferences"} <= case.keys()
        for case in prospective
    )
