"""Local-LLM intent regression; does not require the road database."""

import json
from pathlib import Path

from app.services.local_llm_service import parse_route_intent


CASE_FILES = (
    Path(__file__).with_name("route_intent_holdout.json"),
    Path(__file__).with_name("route_intent_extended.json"),
)


def evaluate() -> tuple[int, int]:
    passed = 0
    total = 0
    for case_file in CASE_FILES:
        cases = json.loads(case_file.read_text(encoding="utf-8"))
        total += len(cases)
        file_passed = 0
        for case in cases:
            success = _evaluate_case(case)
            passed += int(success)
            file_passed += int(success)
        print(f"{case_file.name}: {file_passed}/{len(cases)}")
    print(f"Passed {passed}/{total} route intent cases")
    return passed, total


def _evaluate_case(case: dict[str, object]) -> bool:
    try:
        actual = parse_route_intent(case["query"])
        factors = {item.factor: item.direction for item in actual.preferences}
        expected = case["preferences"]
        checks = {
            "origin": actual.origin_name == case["origin"],
            "destination": actual.destination_name == case["destination"],
            "time": (
                actual.departure_time.isoformat() if actual.departure_time else None
            ) == case.get("time"),
            "preferences": factors == expected,
        }
        success = all(checks.values())
        print(json.dumps({"ok": success, "query": case["query"], "checks": checks,
                          "actual_time": (actual.departure_time.isoformat()
                                          if actual.departure_time else None),
                          "actual_preferences": factors}, ensure_ascii=False))
        return success
    except Exception as exc:
        print(json.dumps({"ok": False, "query": case["query"],
                          "error": str(exc)}, ensure_ascii=False))
        return False


if __name__ == "__main__":
    matched, total = evaluate()
    raise SystemExit(0 if matched == total else 1)
