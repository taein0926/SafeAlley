"""Display actual routing conditions without changing legacy ranking or badges."""

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
    cards = []
    for factor in CARD_ORDER:
        applied = False
        direction = None
        period = None
        if factor == "time":
            applied = selected is not None
            period = "night" if time_context.is_night else "day"
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
                    if arguments.crossing_weight > 0 or selected["route"]["properties"].get("cost_weights", {}).get("crossing", 0) > 0:
                        applied = True
                        direction = direction or "minimize"
        cards.append(ConditionCard(factor=factor, state="applied" if applied else "not_applied", direction=direction, period=period))
    return cards
