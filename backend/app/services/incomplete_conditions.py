"""Conservative guard for a trailing, unfinished list of condition nouns.

This is not a replacement natural-language parser. It only prevents a model
from guessing directions for bare nouns/particles at the end of an input.
"""

import re

NOUN_FACTORS = {
    "계단": "stairs_distance_m", "횡단보도": "crosswalk_count", "건널목": "crosswalk_count",
    "가로등": "streetlight_score", "조명": "streetlight_score", "CCTV": "cctv_score",
    "안전시설": "safety_score", "도움시설": "safety_score", "경찰서": "police_accessibility",
    "파출소": "police_accessibility", "보도": "sidewalk_coverage_percent", "인도": "sidewalk_coverage_percent",
    "경사": "max_slope_percent", "육교": "pedestrian_bridge_count", "거리": "distance_m",
}
_NOUN = "(?:" + "|".join(sorted(NOUN_FACTORS, key=len, reverse=True)) + ")"
_TERM = _NOUN + r"(?:은|는|을|를|이|가|도)?"
_TAIL = re.compile(r"(?<![가-힣])(?P<nouns>" + _TERM + r"(?:\s*(?:와|과|및|그리고|,)?\s*" + _TERM + r")*)\s*[.!?,。！？]*$", re.IGNORECASE)
_MENTION = re.compile(r"(?<![가-힣])" + _NOUN, re.IGNORECASE)
_COMPLETE_CUE = re.compile(r"피하|피해|없이|없는|적게|적은|덜|최소|회피|많|밝|우선|선호|가까|가깝|짧|좋")


def incomplete_condition_factors(query: str) -> set[str]:
    tail = _TAIL.search(query.strip())
    if tail is None:
        return set()
    prefix = query[:tail.start()]
    incomplete = set()
    for mention in _MENTION.finditer(tail.group("nouns")):
        noun = mention.group()
        if noun.upper() == "CCTV":
            noun = "CCTV"
        factor = NOUN_FACTORS[noun]
        # A bare repeated noun must not erase an earlier completed request.
        earlier = [m for m in _MENTION.finditer(prefix)
                   if NOUN_FACTORS.get("CCTV" if m.group().upper() == "CCTV" else m.group()) == factor]
        if earlier and _COMPLETE_CUE.search(prefix[earlier[-1].end():]):
            continue
        incomplete.add(factor)
    return incomplete
