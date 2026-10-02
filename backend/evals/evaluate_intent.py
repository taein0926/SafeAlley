"""Evaluate local-LLM intent parsing without depending on a road database."""

import argparse
import json
from collections import defaultdict
from math import ceil
from pathlib import Path
from time import monotonic

from app.schemas.agent import ParsedRouteIntent
from app.services.local_llm_service import clear_intent_cache, parse_route_intent


EVAL_DIR = Path(__file__).parent
CASE_SETS = {
    "prospective_final_20261002": (EVAL_DIR / "route_intent_prospective_final_20261002.json",),
    "prospective_validation_20261002": (EVAL_DIR / "route_intent_prospective_validation_20261002.json",),
    "prospective_probe_20261002": (EVAL_DIR / "route_intent_prospective_probe_20261002.json",),
    "prospective_reserve_20261002": (EVAL_DIR / "route_intent_prospective_reserve_20261002.json",),
    "time_role_probe": (EVAL_DIR / "route_intent_time_role_probe_20261002.json",),
    "new_questions": (EVAL_DIR / "route_intent_new_questions_20261001.json",),
    "multi_sentence_probe": (EVAL_DIR / "route_intent_multi_sentence_probe_20261001.json",),
    "comparison_probe": (EVAL_DIR / "route_intent_comparison_probe_20261001.json",),
    "prospective": (EVAL_DIR / "route_intent_prospective_20261001.json",),
    "dev": (
        EVAL_DIR / "route_intent_holdout.json",  # historical suite; no longer a blind holdout
        EVAL_DIR / "route_intent_extended.json",
        EVAL_DIR / "route_intent_challenges.json",
    ),
    "regression": (
        EVAL_DIR / "route_intent_holdout_20261001.json",
        EVAL_DIR / "route_intent_holdout_fresh_20261001.json",
        EVAL_DIR / "route_intent_holdout_final_20261001.json",
        EVAL_DIR / "route_intent_holdout_blind_20261001.json",
        EVAL_DIR / "route_intent_prospective_20261001.json",
        EVAL_DIR / "route_intent_holdout_unseen_20261001.json",
        EVAL_DIR / "route_intent_comparison_probe_20261001.json",
        EVAL_DIR / "route_intent_multi_sentence_probe_20261001.json",
        EVAL_DIR / "route_intent_new_questions_20261001.json",
        EVAL_DIR / "route_intent_time_role_probe_20261002.json",
    ),
    "holdout": (EVAL_DIR / "route_intent_holdout_safety_20261001.json",),
}


def score_case(case: dict[str, object], intent: ParsedRouteIntent | None) -> dict[str, object]:
    expected = case["preferences"]
    factors = (
        {item.factor: item.direction for item in intent.preferences}
        if intent is not None else {}
    )
    checks = {
        "origin": intent is not None and intent.origin_name == case["origin"],
        "destination": intent is not None and intent.destination_name == case["destination"],
        "time": intent is not None and (
            intent.departure_time.isoformat() if intent.departure_time else None
        ) == case.get("time"),
        "preferences": intent is not None and factors == expected,
    }
    unrequested = sorted(set(factors) - set(expected))
    missing = sorted(set(expected) - set(factors))
    wrong_direction = sorted(
        factor for factor in set(factors) & set(expected)
        if factors[factor] != expected[factor]
    )
    return {
        "checks": checks,
        "exact": all(checks.values()),
        "unrequested_factors": unrequested,
        "missing_factors": missing,
        "wrong_direction_factors": wrong_direction,
        "hard_false_positive": any(
            direction == "avoid" and expected.get(factor) != "avoid"
            for factor, direction in factors.items()
        ),
        "hard_false_negative": any(
            direction == "avoid" and factors.get(factor) != "avoid"
            for factor, direction in expected.items()
        ),
        "actual_origin": intent.origin_name if intent is not None else None,
        "actual_destination": intent.destination_name if intent is not None else None,
        "actual_time": (
            intent.departure_time.isoformat()
            if intent is not None and intent.departure_time else None
        ),
        "actual_preferences": factors,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, ceil(len(ordered) * fraction) - 1)], 3)


def evaluate(
    case_files: tuple[Path, ...],
    *,
    quiet: bool = False,
    only_ids: set[str] | None = None,
) -> dict[str, object]:
    # The evaluator must measure a fresh model response for every case.
    from app.core.config import get_settings

    get_settings().ollama_intent_cache_seconds = 0
    clear_intent_cache()
    outcomes: list[dict[str, object]] = []
    categories: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "passed": 0,
            "total": 0,
            "field_errors": {field: 0 for field in ("origin", "destination", "time", "preferences")},
            "unrequested_factor_count": 0,
            "missing_factor_count": 0,
            "wrong_direction_count": 0,
        }
    )
    durations: list[float] = []
    for case_file in case_files:
        cases = json.loads(case_file.read_text(encoding="utf-8"))
        for index, case in enumerate(cases):
            case_id = case.get("id", f"{case_file.stem}-{index + 1}")
            if only_ids is not None and case_id not in only_ids:
                continue
            started = monotonic()
            error = None
            intent = None
            try:
                intent = parse_route_intent(case["query"])
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            duration = monotonic() - started
            durations.append(duration)
            scored = score_case(case, intent)
            category = case.get("category", "legacy")
            categories[category]["total"] += 1
            categories[category]["passed"] += int(scored["exact"])
            for field, passed in scored["checks"].items():
                categories[category]["field_errors"][field] += int(not passed)
            categories[category]["unrequested_factor_count"] += len(scored["unrequested_factors"])
            categories[category]["missing_factor_count"] += len(scored["missing_factors"])
            categories[category]["wrong_direction_count"] += len(scored["wrong_direction_factors"])
            outcome = {
                "id": case_id,
                "category": category,
                "source_file": case_file.name,
                "query": case["query"],
                "duration_s": round(duration, 3),
                **scored,
                "error": error,
            }
            outcomes.append(outcome)
            if not quiet:
                print(json.dumps(outcome, ensure_ascii=False))
    total = len(outcomes)
    summary = {
        "passed": sum(item["exact"] for item in outcomes),
        "total": total,
        "field_passed": {
            field: sum(item["checks"][field] for item in outcomes)
            for field in ("origin", "destination", "time", "preferences")
        },
        "hard_false_positive": sum(item["hard_false_positive"] for item in outcomes),
        "hard_false_negative": sum(item["hard_false_negative"] for item in outcomes),
        "unrequested_factor_count": sum(
            len(item["unrequested_factors"]) for item in outcomes
        ),
        "missing_factor_count": sum(
            len(item["missing_factors"]) for item in outcomes
        ),
        "wrong_direction_count": sum(
            len(item["wrong_direction_factors"]) for item in outcomes
        ),
        "categories": dict(categories),
        "latency_s": {
            "p50": _percentile(durations, 0.5),
            "p95": _percentile(durations, 0.95),
        },
        "failed_ids": [item["id"] for item in outcomes if not item["exact"]],
        "errors": sum(item["error"] is not None for item in outcomes),
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=(*CASE_SETS, "all"), default="dev")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--ids", help="Comma-separated case IDs for targeted diagnosis")
    args = parser.parse_args()
    files = (
        CASE_SETS["dev"] + CASE_SETS["regression"] + CASE_SETS["holdout"]
        if args.set == "all" else CASE_SETS[args.set]
    )
    ids = set(args.ids.split(",")) if args.ids else None
    result = evaluate(files, quiet=args.quiet, only_ids=ids)
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
