"""Distinguish executed soft routing costs from complete metric comparisons."""

import math

from app.schemas.intent_preview import CARD_ORDER, ConditionCard


METRIC_FACTORS = {
    "distance": ("distance_m", {"minimize"}),
    "safety": ("safety_score", {"maximize"}),
    "streetlight": ("streetlight_score", {"maximize"}),
    "cctv": ("cctv_score", {"maximize"}),
    "stairs": ("stairs_distance_m", {"avoid", "minimize"}),
    "crossing": ("crosswalk_count", {"avoid", "minimize"}),
}


def routing_condition_cards(selected, preferences, unsupported, arguments, time_context) -> list[ConditionCard]:
    excluded = {item.factor for item in unsupported}
    by_factor = {item.factor: item for item in preferences}
    explicit_only = getattr(arguments, "preference_mode", "personalized") == "explicit_only"
    cards = []
    for factor in CARD_ORDER:
        applied = False
        direction = None
        period = None
        scope = None
        quality = None
        reason = None
        if factor == "time":
            applied = selected is not None and (not explicit_only or getattr(arguments, "departure_time", None) is not None)
            period = "night" if time_context.is_night else "day"
            if applied:
                reason = ("지정한 출발 시각으로 주간·야간 정책을 적용했습니다" if getattr(arguments, "departure_time", None) is not None
                          else "출발 시각을 지정하지 않아 현재 시각으로 주간·야간 정책을 적용했습니다")
        # Bridge preferences are recognized in previews, not independently costed in routing.
        elif factor != "bridge" and selected is not None:
            metric, directions = METRIC_FACTORS[factor]
            preference = by_factor.get(metric)
            value = selected["metrics"].get(metric)
            if metric not in excluded and value is not None:
                if preference and preference.direction in directions:
                    direction = preference.direction
                    applied = not (direction == "avoid" and value > 0)
                if factor == "stairs" and arguments.stairs_weight > 0:
                    applied = True
                    direction = direction or "minimize"
                if factor == "crossing" and selected["route"]["properties"].get("crossing_data_available"):
                    if arguments.crossing_weight > 0 or (not explicit_only or preference is not None) and selected["route"]["properties"].get("cost_weights", {}).get("crossing", 0) > 0:
                        applied = True
                        direction = direction or "minimize"
        if factor == "crossing" and selected is not None:
            preference = by_factor.get("crosswalk_count")
            properties = selected["route"]["properties"]
            cost = properties.get("cost_weights", {}).get("crossing", 0)
            count = properties.get("total_crosswalk_count")
            valid_cost = isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost > 0
            valid_count = isinstance(count, int) and not isinstance(count, bool) and count >= 0
            # Incomplete observations never prove a hard zero-crossing constraint.
            requested_soft = preference is not None and preference.direction == "minimize"
            implicit_cost_allowed = preference is None and (not explicit_only or arguments.crossing_weight > 0)
            if (requested_soft or implicit_cost_allowed) and valid_cost and valid_count:
                applied, direction, scope = True, "minimize", "route_generation"
                quality = "complete" if properties.get("crossing_data_available") else "partial"
        cards.append(ConditionCard(factor=factor, state="applied" if applied else "not_applied", direction=direction, period=period,
                                   application_scope=scope, data_quality=quality, reason=reason))
    return cards
