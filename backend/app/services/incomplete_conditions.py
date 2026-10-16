"""Conservative guard for a trailing, unfinished list of condition nouns.

This is not a replacement natural-language parser. It only prevents a model
from guessing directions for bare nouns/particles at the end of an input.
"""

import re
from typing import Literal

NOUN_FACTORS = {
    "계단": "stairs_distance_m", "층계": "stairs_distance_m",
    "횡단보도": "crosswalk_count", "건널목": "crosswalk_count",
    "가로등": "streetlight_score", "조명": "streetlight_score", "CCTV": "cctv_score",
    "씨씨티비": "cctv_score", "감시카메라": "cctv_score",
    "안전시설": "safety_score", "도움시설": "safety_score", "경찰서": "police_accessibility",
    "파출소": "police_accessibility", "보도": "sidewalk_coverage_percent", "인도": "sidewalk_coverage_percent",
    "육교": "pedestrian_bridge_count",
    "고가보도": "pedestrian_bridge_count", "거리": "distance_m",
}
_NOUN = "(?:" + "|".join(sorted(NOUN_FACTORS, key=len, reverse=True)) + ")"
_TERM = _NOUN + r"(?:은|는|을|를|이|가|도)?"
_TAIL = re.compile(r"(?<![가-힣])(?P<nouns>" + _TERM + r"(?:\s*(?:와|과|및|그리고|,)?\s*" + _TERM + r")*)\s*[.!?,。！？]*$", re.IGNORECASE)
_MENTION = re.compile(r"(?<![가-힣])" + _NOUN, re.IGNORECASE)
_COMPLETE_CUE = re.compile(r"피하|피해|없이|없는|적게|적은|덜|최소|회피|많|밝|우선|선호|가까|가깝|짧|좋")
PreviewEvidence = Literal["absent", "mentioned", "incomplete", "positive", "negative"]

_HELP_FACILITY = (
    r"(?:경찰서|지구대|파출소|치안\s*센터|치안\s*시설|소방서|119\s*안전\s*센터"
    r"|응급실|응급\s*의료\s*(?:기관|시설)|병원)"
)
_PREVIEW_MENTIONS = {
    # Bare "가까운 길" is intentionally excluded.  In "경찰서가 가까운 길"
    # it describes facility proximity, not a short origin-to-destination route.
    "distance": re.compile(
        r"최단\s*(?:거리|경로|길)|짧(?:은|게|고)?\s*(?:길|경로)?|빠른\s*(?:길|경로)"
        r"|빠르게|빨리|신속|지름길|(?:가장|최대한|가능한|더)\s*가까운\s*(?:길|경로)"
    ),
    "safety": re.compile(
        r"안전\s*시설|도움\s*(?:요청\s*)?시설|치안\s*시설|안전한\s*(?:길|경로)"
        r"|안전하게|위험하지\s*않(?:은|게)|안심|위급할\s*때\s*도움"
        r"|" + _HELP_FACILITY
        + r"(?:은|는|이|가|와|과|에|을|를)?\s*(?:더\s*)?"
        r"(?:가까|많|접근|우선|주변|근처|인근|옆|경유|지나)"
        r"|(?:가까운|많은|접근하기\s*좋은|주변|근처|인근)\s*" + _HELP_FACILITY
    ),
    "streetlight": re.compile(
        r"가로등|조명|밝은\s*(?:길|경로)|어두운\s*(?:길|경로)|환한\s*(?:길|경로)"
        r"|밝(?:게|고|았|으면)|환(?:하(?:고|며|게|면)|했)"
    ),
    "cctv": re.compile(
        r"CCTV|씨씨티비|감시\s*카메라|방범\s*(?:카메라|시설)|폐쇄회로\s*(?:TV|텔레비전)",
        re.IGNORECASE,
    ),
    "stairs": re.compile(r"계단|층계"),
    "crossing": re.compile(r"횡단보도|건널목"),
    "bridge": re.compile(r"육교|고가\s*보도|보행\s*육교"),
    "time": re.compile(
        r"오전|오후|밤|낮|새벽|아침|저녁|야간|자정|정오"
        r"|\d{1,2}\s*(?:시|:\s*\d{2})"
        r"|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두)\s*시"
    ),
}
_PREVIEW_METRICS = {
    "distance": "distance_m", "safety": "safety_score", "streetlight": "streetlight_score",
    "cctv": "cctv_score", "stairs": "stairs_distance_m", "crossing": "crosswalk_count",
    "bridge": "pedestrian_bridge_count",
}
_CANCEL_CUE = re.compile(
    r"필요(?:는|가)?\s*없|상관\s*없|고려하지\s*(?:않|마)|빼고|무시|중요하지\s*않"
    r"|피하(?:지|진)\s*(?:않|말)|있어도\s*(?:괜찮|돼|되)|건너도\s*(?:괜찮|돼|되)"
    r"|피하(?:고)?\s*싶지\s*않|피할\s*(?:생각|마음|의향)(?:은|이)?\s*없"
    r"|많지\s*않아도|밝지\s*않아도|원하지\s*않|아니어도\s*(?:돼|되|괜찮)"
    r"|고려\s*(?:안|하지\s*않)|굳이.{0,12}(?:필요\s*없|않아도\s*(?:돼|되))"
    r"|(?:안\s*(?:할래|할게|하겠|해도)|하지\s*않(?:을게|을래|겠다)|신경\s*쓰지\s*마)"
    r"|(?:줄일|피할|회피할|우선할|고려할)\s*(?:생각|마음|의향)(?:은|이)?\s*없"
    r"|싫지\s*않|없어도\s*(?:돼|되|괜찮)|아니(?:야|고|라|라서)"
    r"|(?:많|밝|가까|없|적|어두).{0,10}(?:싫|괜찮|상관\s*없)"
)
_POSITIVE_CUES = {
    "distance": re.compile(r"최단|짧|빠르|빠르게|빨리|신속|가까운|지름길"),
    "safety": re.compile(r"가까|가깝|근처|주변|인근|옆|경유|지나|접근|많|우선|고려|안전|안심|위험하지|도움|보호"),
    "streetlight": re.compile(r"많|밝|환한|환하|환했|잘\s*(?:된|갖춰)|충분|우선|가까|어두.{0,8}(?:피하|싫)|최대"),
    "cctv": re.compile(r"많|마는\s*(?:길|경로)|우선|가까|접근|최대"),
    "stairs": re.compile(r"피하|피할|없이|없는|안\s*가|안가|적|최소|줄|회피|싫|말고|빼고"),
    "crossing": re.compile(r"피하|피할|없이|없는|적|최소|줄|회피|싫|말고|빼고"),
    "bridge": re.compile(r"이용|거쳐|통해|우선|육교(?:으)?로|피하|피할|없이|없는|적|최소|회피|싫|말고|빼고"),
}
_INVERSE_CUES = {
    "safety": re.compile(r"적(?:고|은|게)|없(?:고|는|이|는\s*길)|멀(?:고|리|게)|피하"),
    "streetlight": re.compile(r"적(?:고|은|게)|없(?:고|는|이)|어두(?:운|워)"),
    "cctv": re.compile(r"적(?:고|은|게)|없(?:고|는|이)|피하"),
    "stairs": re.compile(r"많(?:고|은|게)"),
    "crossing": re.compile(r"많(?:고|은|게)|(?:횡단보도|건널목)(?:으)?로"),
}
_LEADING_CUE = re.compile(r"(?:가까운|많은|적은|없는|밝은|어두운|환한|짧은|빠른)\s*$")
_KOREAN_HOURS = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6,
    "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "열한": 11, "열두": 12,
}
_KOREAN_HOUR_PATTERN = "|".join(sorted(_KOREAN_HOURS, key=len, reverse=True))
_EXPLICIT_CLOCK = re.compile(
    r"(?:(?:오전|오후|밤|낮|새벽|아침|저녁)\s*)?"
    r"(?:\d{1,2}|" + _KOREAN_HOUR_PATTERN + r")\s*(?:시|:\s*\d{2})|자정|정오"
)


def _is_cancelled(factor: str, phrase: str, after: str) -> bool:
    """Recognize a non-request without treating every Korean '말고' alike."""
    # Disliking darkness is a positive lighting request, unlike disliking a
    # well-lit route.  Handle this before the generic "...싫어" cancellation.
    if factor == "streetlight" and re.search(r"어두.{0,10}싫", phrase):
        return False
    # For obstacle cards, "계단/건널목/육교 빼고" means route avoidance,
    # not cancellation of the corresponding condition.
    if factor in {"stairs", "crossing", "bridge"} and re.match(
        r"\s*(?:은|는|이|가|을|를|도)?\s*빼고", after
    ):
        return False
    # "A보다(는) B가 좋다" explicitly deprioritizes A.  Restrict this to
    # preference cards: for obstacle cards, a comparison alone does not say
    # whether the user wants to avoid either obstacle.
    if factor in {"distance", "safety", "streetlight", "cctv"}:
        if re.match(r"\s*(?:보다(?:는)?|보단|대신)", after):
            return True
        if re.search(r"싫", after):
            return True
    if _CANCEL_CUE.search(after):
        return True
    if re.match(r"\s*(?:은|는|이|가|도)?\s*(?:괜찮|상관\s*없)", after):
        return True
    if re.search(
        r"안\s*(?:피하|피해|피할|줄이|줄일|줄여|우선하|우선할|고려하|고려할|이용하|이용할)"
        r".{0,8}(?:래|게|겠다|거야|돼|괜찮)",
        after,
    ):
        return True
    if "말고" not in after:
        return False
    # For obstacle cards, "계단/건널목/육교 말고" is an avoidance request.
    # For desirable cards, "최단거리/CCTV 말고" rejects that preference.
    return factor not in {"stairs", "crossing", "bridge"}


def _clock_hour(phrase: str) -> int | None:
    numeric = re.search(r"(\d{1,2})\s*(?:시|:)", phrase)
    if numeric:
        return int(numeric.group(1))
    korean = re.search(r"(" + _KOREAN_HOUR_PATTERN + r")\s*시", phrase)
    return _KOREAN_HOURS[korean.group(1)] if korean else None


def _shared_correction_choice(query: str, factor: str) -> str | None:
    """Resolve an explicit final '둘 다' correction for two named cards."""
    correction = re.search(
        r"(?:아니\s*[,，]?\s*|그냥\s*)?둘\s*다\s*"
        r"(?P<tail>.{0,24})$",
        query,
    )
    if correction is None:
        return None
    mentioned = {
        name for name, pattern in _PREVIEW_MENTIONS.items()
        if pattern.search(query[:correction.start()])
    }
    if factor not in mentioned or len(mentioned) < 2:
        return None
    tail = correction.group("tail")
    if factor in {"distance", "safety", "streetlight", "cctv"} and re.search(
        r"많|밝|환|가까|안전|우선|좋", tail
    ):
        return "apply"
    if factor in {"stairs", "crossing", "bridge"}:
        if re.search(r"없이|없는|피하|회피", tail):
            return "avoid"
        if re.search(r"적|덜|최소|줄", tail):
            return "minimize"
    return None


def _preview_scope(query: str, factor: str) -> tuple[str, str, re.Match[str]] | None:
    mentions = list(_PREVIEW_MENTIONS[factor].finditer(query))
    if not mentions:
        return None
    mention = mentions[-1]
    end = len(query)
    for other_factor, pattern in _PREVIEW_MENTIONS.items():
        if other_factor == factor:
            continue
        following = pattern.search(query, mention.end())
        if following:
            end = min(end, following.start())
    boundary = re.search(r"[.!?]", query[mention.end():end])
    if boundary:
        end = mention.end() + boundary.start()
    return query[max(0, mention.start() - 18):mention.start()], query[mention.end():end], mention


def preview_factor_evidence(query: str, factor: str) -> tuple[PreviewEvidence, str | None]:
    """Return source evidence for one fixed preview card.

    This is deliberately a high-precision guard around Jev, not a second
    general-purpose parser.  It prevents an unmentioned card from lighting up
    and recognizes only clear completion, cancellation and time expressions.
    """
    if factor not in _PREVIEW_MENTIONS:
        return "absent", None
    shared_choice = _shared_correction_choice(query, factor)
    if shared_choice is not None:
        return "positive", shared_choice
    scope = _preview_scope(query, factor)
    if scope is None:
        return "absent", None
    before, after, mention = scope
    # Only an adjective directly attached before the current factor belongs to
    # it.  A broad look-behind incorrectly assigned an earlier clause such as
    # '도움시설 적고' to the later '건널목'.
    leading = _LEADING_CUE.search(before)
    phrase = ((before if factor == "time" else leading.group() if leading else "")
              + mention.group() + after)
    if _is_cancelled(factor, phrase, after):
        return "negative", "skip"
    metric = _PREVIEW_METRICS.get(factor)
    if metric and metric in incomplete_condition_factors(query):
        return "incomplete", "pending"
    if factor == "time":
        if re.search(r"저녁|야간", phrase) and not _EXPLICIT_CLOCK.search(phrase):
            return "positive", "night"
        period = re.search(
            r"(오전|오후|밤|낮|새벽|아침)\s*"
            r"(?:에|으로|부터|동안|(?=(?:출발|이동|갈|가(?:자|줘|려고|는)|걷)))",
            phrase,
        )
        if period and not _EXPLICIT_CLOCK.search(phrase):
            return "positive", "night" if period.group(1) in {"밤", "새벽"} else "day"
        if not _EXPLICIT_CLOCK.search(phrase):
            return "incomplete", "pending"
        clocks = list(_EXPLICIT_CLOCK.finditer(query))
        clock_phrase = clocks[-1].group() if clocks else phrase
        hour = _clock_hour(clock_phrase)
        if re.search(r"밤|새벽|저녁|야간|자정", clock_phrase):
            night = True
        elif re.search(r"낮|아침|정오", clock_phrase):
            night = False
        else:
            if hour is not None and "오후" in clock_phrase and hour < 12:
                hour += 12
            elif hour is not None and "오전" in clock_phrase and hour == 12:
                hour = 0
            night = hour is not None and (hour >= 19 or hour < 6)
        return "positive", "night" if night else "day"
    positive = _POSITIVE_CUES[factor].search(phrase)
    inverse = _INVERSE_CUES.get(factor)
    # '어두운 길을 피한다' is a positive lighting request; otherwise an
    # explicitly inverse/unsafe direction is not a supported applied card.
    if inverse and inverse.search(phrase) and not (
        factor == "streetlight" and re.search(r"어두.{0,10}(?:피하|싫)", phrase)
    ):
        return "negative", "skip"
    if not positive:
        return "mentioned", None
    if factor in {"stairs", "crossing", "bridge"}:
        direction = "avoid" if re.search(r"없이|없는|안\s*가|안가|피하|피할|회피|싫|말고|빼고", phrase) else "minimize"
        if factor == "bridge" and re.search(r"이용|거쳐|통해|우선|육교(?:으)?로", phrase) and not re.search(r"피하|회피|없이|없는|적|최소", phrase):
            direction = "apply"
        return "positive", direction
    return "positive", "apply"


def has_explicit_safety_facility_request(query: str) -> bool:
    """Confirm an explicit help-facility preference without inventing one.

    Jev and the final LLM remain the natural-language interpreters.  This
    narrow check only reconciles an unambiguous facility-proximity phrase and
    honors a cancellation attached to the last facility mention.
    """
    evidence, _ = preview_factor_evidence(query, "safety")
    if evidence != "positive":
        return False
    # Police proximity already has a dedicated router factor.  It can light
    # the combined preview card without silently adding a second safety_score
    # preference to the final structured intent.
    return not re.search(r"경찰서|지구대|파출소|치안\s*(?:센터|시설)", query)


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
