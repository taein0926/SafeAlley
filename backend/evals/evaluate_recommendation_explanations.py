"""Deterministic regression checks for user-facing route explanations."""

import json
from pathlib import Path

from app.schemas.agent import RoutePreference, UnsupportedPreference
from app.services.route_ranking_service import (
    _comparison_candidate,
    _recommendation_criteria,
    _recommendation_explanation,
)


CASES_PATH = Path(__file__).with_name("recommendation_explanation_cases.json")


def _candidate(payload: dict[str, object], index: int) -> dict[str, object]:
    route_type = str(payload["route_type"])
    return {
        "route_type": route_type,
        "preference_score": payload.get("score"),
        "metrics": payload["metrics"],
        "route": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[126.6, 37.4], [126.6 + index / 1000, 37.401]],
            },
            "properties": {
                "unverified_major_road_count": payload.get("unverified", 0),
                "road_segments": [{"source_id": f"{route_type}-{index}"}],
            },
        },
    }


def _evaluate_case(case: dict[str, object]) -> bool:
    candidates = [
        _candidate(payload, index)
        for index, payload in enumerate(case["candidates"], start=1)
    ]
    selected = next(
        (
            candidate for candidate in candidates
            if candidate["route_type"] == case.get("selected_type")
        ),
        None,
    )
    preferences = [RoutePreference.model_validate(item) for item in case["preferences"]]
    unsupported = [
        UnsupportedPreference.model_validate(item)
        for item in case.get("unsupported", [])
    ]
    supported = [
        item for item in preferences
        if item.factor not in {entry.factor for entry in unsupported}
    ]
    comparison = _comparison_candidate(selected, candidates, supported)
    reason, notes = _recommendation_explanation(
        selected,
        candidates,
        preferences,
        unsupported,
        str(case["status"]),
        None,
    )
    criteria = _recommendation_criteria(
        selected, comparison, preferences, unsupported,
    )
    outcomes = {item["factor"]: item["outcome"] for item in criteria}
    all_text = " ".join([reason, *notes])
    checks = {
        "reason": all(text in reason for text in case.get("reason_contains", [])),
        "notes": all(
            any(text in note for note in notes)
            for text in case.get("notes_contains", [])
        ),
        "forbidden": all(text not in all_text for text in case.get("forbidden", [])),
        "criteria": all(
            outcomes.get(factor) == outcome
            for factor, outcome in case.get("criteria", {}).items()
        ),
        "comparison": (
            comparison["route_type"] if comparison else None
        ) == case.get("compared_route_type"),
    }
    success = all(checks.values())
    print(json.dumps({
        "ok": success,
        "name": case["name"],
        "checks": checks,
        "reason": reason,
        "criteria": outcomes,
    }, ensure_ascii=False))
    return success


def evaluate() -> tuple[int, int]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    passed = sum(_evaluate_case(case) for case in cases)
    print(f"Passed {passed}/{len(cases)} recommendation explanation cases")
    return passed, len(cases)


if __name__ == "__main__":
    matched, total = evaluate()
    raise SystemExit(0 if matched == total else 1)
