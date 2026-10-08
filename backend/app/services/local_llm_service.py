import json
import logging
import re
from collections import OrderedDict
from datetime import time
from threading import Lock
from time import monotonic

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.agent import ParsedRouteIntent, RoutePreference


class LocalLLMUnavailableError(RuntimeError):
    """Raised when the configured local Ollama service cannot be reached."""


class LocalLLMOutputError(RuntimeError):
    """Raised when the model response does not satisfy the structured schema."""


SYSTEM_PROMPT = """한국어 보행 요청을 JSON으로만 추출한다. 좌표/SQL/도구를 만들지 않는다.
사용자가 말한 출발지=origin_name, 도착지=destination_name. 장소를 추측하지 않는다.
장소명은 문장에 실제 나온 문자열 그대로 적는다. 한쪽이 없으면 null이다.
시각=departure_time(HH:MM:SS, 시간대 없음). 밤 10시=22:00:00, 오전 6시30분=06:30:00.
밤 10시 반=22:30:00, 오전 12시=00:00:00, 오후 12시=12:00:00,
자정=00:00:00, 정오=12:00:00.
시각이 없으면 departure_time은 반드시 null이다. 00:00:00이나 현재 시각을 만들어 넣지 않는다.
조건은 preferences의 factor/direction으로 모두 보존한다. 요청하지 않은 조건은 만들지 않는다.
각 공간 요소를 추출하기 전에 문장 속 역할을 구분한다: 원하는 기준, 허용하는 상황,
중요하지 않은 요소, 다른 기준과 비교해서 제외한 요소. 원하는 기준만 preferences에 넣는다.
어떤 요소가 있어도/없어도 괜찮다는 허용이지 그 요소를 줄이거나 늘려 달라는 요청이 아니다.
A보다 B를 원하면 A를 넣지 않는다. A도 중요하고 B도 중요하다고 하면 둘 다 넣는다.
특정 시설에 가까운 길은 시설 접근성 요청이지 출발지-도착지 최단거리 요청이 아니다.
단순히 안내해 달라는 요청도 distance_m 조건이 아니다. 기본 경로 정책은 백엔드가 정한다.
단어의 등장 횟수나 부정어만으로 조건을 추측하지 않는다.
factor: 최단/짧은 길/빠른 길/가까운 길/거리=distance_m,
안전=safety_score, 조명/가로등=streetlight_score,
CCTV=cctv_score, 건널목/횡단보도=crosswalk_count, 계단=stairs_distance_m,
보도/인도=sidewalk_coverage_percent,
경사/평지/완만한 길=max_slope_percent, 경찰서 접근성=police_accessibility.
police_accessibility는 접근하기 좋은 정도다. 경찰서가 가까운 길은 maximize이며,
시설까지의 거리를 뜻하는 값이 아니다. 경찰서를 피하는 요청은 avoid로 보존한다.
미지원 조건도 snake_case factor로 보존한다. flatness는 쓰지 않는다.
direction: 적게/짧게/평지=minimize, 많게/밝게/안전하게=maximize, 없이/피해/없는 길=avoid.
각 조건에 인접한 수식어를 적용: 횡단보도는 적고 CCTV가 많은=각각 minimize, maximize.
계단을 피하지 말라는 것은 계단 회피 요청이 아니다. 평지가 필요 없다는 것도 경사 조건이 아니다.
횡단보도를 건너도 괜찮다, 평지가 아니어도 된다는 허용 표현도 회피/경사 조건이 아니다.
최단거리 말고/짧은 길보다는 다른 조건을 우선한다면 distance_m을 넣지 않는다.
조금 멀어져도 괜찮다는 말도 거리 최소화 요청이 아니다.
너무 멀리 돌아가지 않게는 distance_m/minimize도 함께 보존한다.
어두운 길을 피하는 것은 조명 부족을 피한다는 뜻이므로 streetlight_score/maximize다.
계단 적게=minimize, 계단 없이=avoid. 건널목/횡단보도 회피·가급적 피해=minimize,
건널목/횡단보도 없이·절대 건너지 않기=avoid. 여기서 건널목은 철도가 아닌 보행 횡단보도다.
시간/장소/profile은 factor가 아니다.
휠체어 통행=wheelchair_accessibility/maximize, 유모차 통행=stroller_accessibility/maximize,
실시간 교통체증=traffic_congestion/minimize. 휠체어와 유모차는 서로 바꿔 쓰지 않는다.
엘리베이터가 있는 길=elevator_accessibility/maximize, 사람이 덜 붐비는 길=crowd_density/minimize.
이 조건들은 현재 경로 지표가 없더라도 다른 지원 지표로 바꾸지 말고 요청 자체를 보존한다.
중요도가 명시된 경우만 weight(0.1~100)를 출력한다. 기본값 1은 생략한다.
profile은 서버가 pedestrian으로 채우므로 생략한다. 문장에 없는 장소는 null이다.
공백/설명 없이 최소 JSON을 출력하되 명시된 조건은 절대 생략하지 않는다.
예: 밤 10시에 주안역에서 인천사랑병원까지 계단 없이 CCTV가 많은 길
{"origin_name":"주안역","destination_name":"인천사랑병원","departure_time":"22:00:00","preferences":[{"factor":"stairs_distance_m","direction":"avoid"},{"factor":"cctv_score","direction":"maximize"}]}
예: 주안역에서 인천사랑병원까지 최단 경로
{"origin_name":"주안역","destination_name":"인천사랑병원","departure_time":null,"preferences":[{"factor":"distance_m","direction":"minimize"}]}
"""


logger = logging.getLogger(__name__)
_INTENT_CACHE_MAX_SIZE = 128
_intent_cache: OrderedDict[tuple[str, str, str, str], tuple[float, str]] = OrderedDict()
_intent_cache_lock = Lock()


def clear_intent_cache() -> None:
    with _intent_cache_lock:
        _intent_cache.clear()


KOREAN_HOURS = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6,
                "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "열한": 11, "열두": 12}
KOREAN_CLOCK_PATTERN = re.compile(
    r"(?<![가-힣])(" + "|".join(sorted(KOREAN_HOURS, key=len, reverse=True)) + r")\s*시"
)


def _clock_text(query: str) -> str:
    """Normalize native Korean hour numerals only for clock validation.

    The original query/place strings sent to the model are not rewritten.
    """
    return KOREAN_CLOCK_PATTERN.sub(lambda m: f"{KOREAN_HOURS[m.group(1)]}시", query)


EXPLICIT_TIME_PATTERN = re.compile(
    r"(?:(?:오전|오후|밤|새벽)\s*)?\d{1,2}\s*(?:시|:\s*\d{2})"
)
EXPLICIT_PERIOD_HOUR_PATTERN = re.compile(
    r"(밤|오후|오전|새벽|아침)\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분|\s*(반))?"
)
TIME_CORRECTION = re.compile(r"아니라|말고|대신|정정|변경|바꿔|바꿨")
ARRIVAL_AFTER_TIME = re.compile(
    r"^\s*(?:에|까지)?(?:(?!출발)[^.?!]){0,35}?도착"
)
DEPARTURE_AFTER_TIME = re.compile(r"^\s*(?:에|부터)?\s*출발")
ARRIVAL_BEFORE_TIME = re.compile(r"도착\s*(?:시각|시간)?(?:은|는|이|가)?\s*$")
DEPARTURE_BEFORE_TIME = re.compile(r"출발\s*(?:시각|시간)?(?:은|는|이|가)?\s*$")
ROUTE_PLACE_PATTERN = re.compile(r"\S.+?에서\s+\S.+?까지")
STAIRS_DISCLAIMER = re.compile(
    r"계단(?:이|은|는|을|를|가)?\s*"
    r"(?:피하(?:지|진)\s*(?:말|않|안)|피할\s*필요(?:는|가)?\s*없|있어도\s*(?:괜찮|돼|되))"
)
CROSSING_DISCLAIMER = re.compile(
    r"(?:횡단보도|건널목)(?:이|은|는|을|를|가)?\s*"
    r"(?:피하(?:지|진)\s*(?:말|않|안)|피할\s*필요(?:는|가)?\s*없"
    r"|건너도\s*(?:괜찮|돼|되))"
)
FLAT_DISCLAIMER = re.compile(
    r"평지(?:는|가|일)?\s*(?:필요(?:는|가)?\s*없|아니어도\s*(?:괜찮|돼|되))"
)
DISTANCE_COMPARISON = re.compile(
    r"(?:최단거리|(?:가장\s*)?짧은\s*길|가장\s*가까운\s*길)\s*"
    r"(?:보단|보다는?|말고)"
)
DISTANCE_CONCESSION = re.compile(
    r"(?:좀|조금|약간)?\s*(?:멀어져도|멀리\s*돌아가도)\s*(?:괜찮|돼|되어)"
)
AVOID_DARK_ROAD = re.compile(r"어두운\s*길(?:을|은)?\s*(?:피하(?!지|진)|싫)")
AVOID_DETOUR = re.compile(
    r"(?:너무\s*)?(?:멀리|먼\s*길로)(?:\s*빙)?\s*돌아가(?:지|지는|진)\s*(?:않|말)"
)
NEARBY_FACILITY_ROUTE = re.compile(
    r"(?:경찰서|파출소|병원|도움\s*시설|CCTV|가로등)\s*(?:와|에)?\s*"
    r"가까운\s*(?:길|경로)"
)
FACTOR_MENTIONS = {
    "distance_m": re.compile(r"최단거리|가까운\s*길|짧(?:은\s*길|고|게)|빠른\s*길|거리"),
    "stairs_distance_m": re.compile(r"계단"),
    "crosswalk_count": re.compile(r"횡단보도|건널목"),
    "streetlight_score": re.compile(r"가로등|조명|밝기|밝은\s*길|어두운\s*길"),
    "cctv_score": re.compile(r"CCTV", re.IGNORECASE),
    "sidewalk_coverage_percent": re.compile(r"보도|인도"),
    "max_slope_percent": re.compile(r"평지|경사"),
    "police_accessibility": re.compile(r"경찰서|파출소"),
    "safety_score": re.compile(r"안전"),
}
NONREQUEST_TAIL = re.compile(
    r"(?:있어도|건너도|건너는\s*건|거쳐도|적어도|많아도|아니어도|없어도|지나도|지나가도)"
    r".{0,10}(?:괜찮|상관\s*없|무방|돼|되)"
    r"|많든\s*적든.{0,8}(?:괜찮|상관\s*없)"
    r"|중요하지\s*않|필요(?:가|는)?\s*없|상관\s*없|피하(?:지|진)\s*(?:않|말)"
    r"|신경\s*안\s*써도|따지지\s*않|고려하지\s*않|말고|빼고|무시하고"
)
CORRECTION_CUE = re.compile(
    r"아니(?:\s*[,，]\s*|\s+)|정정할게\s*[,，]?\s*"
    r"|다시\s*말하면\s*|다시\s*생각해\s*보니\s*|정확히는\s*"
    r"|(?:생각|마음).{0,10}바뀌[가-힣]{0,4}\s*[.!?]?\s*"
)
REJECTED_COMPARISON_TAIL = re.compile(r"보(?:다|다는?|단)")
SENTENCE_BOUNDARY = re.compile(r"[.!?]")
EXPLICIT_SHORT_ROUTE = re.compile(
    r"최단\s*(?:거리|경로|길)|(?:가장\s*)?짧(?:은\s*(?:길|경로)|게)"
    r"|(?:길|경로)보다\s*짧고"
)


def _set_preference(intent: ParsedRouteIntent, factor: str, direction: str) -> None:
    for preference in intent.preferences:
        if preference.factor == factor:
            preference.direction = direction
            return
    if len(intent.preferences) < 20:
        intent.preferences.append(RoutePreference(factor=factor, direction=direction))


def _drop_preference(intent: ParsedRouteIntent, factor: str) -> None:
    intent.preferences = [item for item in intent.preferences if item.factor != factor]


def _last_factor_scope(query: str, factor: str) -> str:
    """Read the final mention of a route factor before enforcing an earlier request."""
    mentions = list(FACTOR_MENTIONS[factor].finditer(query))
    return query[mentions[-1].start():] if mentions else ""


def _is_nonrequest_tail(factor: str, tail: str) -> bool:
    # "계단은 빼고" excludes stairs from the route, unlike
    # "CCTV는 빼고", which removes a preference.
    if factor in {"stairs_distance_m", "crosswalk_count"} and re.match(
        r"^\s*(?:은|는|을|를|도)?\s*빼고", tail
    ):
        return False
    return bool(NONREQUEST_TAIL.search(tail))


def _reconcile_disclaimed_preferences(query: str, intent: ParsedRouteIntent) -> None:
    """Remove only explicit non-requests; never infer a negative from a bare noun."""
    if STAIRS_DISCLAIMER.search(query):
        if re.search(r"계단.{0,14}(?:적게|적은|최소)", query):
            _set_preference(intent, "stairs_distance_m", "minimize")
        else:
            _drop_preference(intent, "stairs_distance_m")
    if CROSSING_DISCLAIMER.search(query):
        if re.search(r"(?:횡단보도|건널목).{0,14}(?:적게|적은|최소)", query):
            _set_preference(intent, "crosswalk_count", "minimize")
        else:
            _drop_preference(intent, "crosswalk_count")
    if FLAT_DISCLAIMER.search(query) and not re.search(r"경사.{0,14}(?:낮|완만|적)", query):
        _drop_preference(intent, "max_slope_percent")
        _drop_preference(intent, "flatness")
    if DISTANCE_COMPARISON.search(query) or DISTANCE_CONCESSION.search(query):
        _drop_preference(intent, "distance_m")


def _normalize_explicit_route_preferences(query: str, intent: ParsedRouteIntent) -> None:
    """Map an explicit supported request to the factor the router actually accepts."""
    for item in list(intent.preferences):
        if item.factor == "stairs_count" and item.direction in {"avoid", "minimize"}:
            _drop_preference(intent, "stairs_count")
            _set_preference(intent, "stairs_distance_m", item.direction)
    # Preserve the existing repair retry for explicit "평지" requests, where
    # the first model response may also have omitted another named condition.
    if "평지" not in query and any(item.factor == "flatness" for item in intent.preferences):
        _drop_preference(intent, "flatness")
        _set_preference(intent, "max_slope_percent", "minimize")
    if re.search(r"계단(?:이|은|는|을|를|가)?\s*(?:적게|적은|적고|최소)", query):
        _drop_preference(intent, "stairs_count")
        _set_preference(intent, "stairs_distance_m", "minimize")
    if re.search(r"경사.{0,12}(?:완만|낮|적)", query):
        _set_preference(intent, "max_slope_percent", "minimize")
    if NEARBY_FACILITY_ROUTE.search(query) and not re.search(
        r"최단|짧은\s*(?:길|경로)|빠른\s*(?:길|경로)|거리|멀리\s*돌아", query
    ):
        _drop_preference(intent, "distance_m")


def _preserve_explicit_short_route(query: str, intent: ParsedRouteIntent) -> None:
    """Restore a directly requested short route, not a rejected comparison option."""
    for match in EXPLICIT_SHORT_ROUTE.finditer(query):
        tail = query[match.end():match.end() + 20]
        if re.match(r"\s*(?:보(?:다|다는?|단)|말고)", tail):
            continue
        # Do not reinterpret a standalone non-request as a request.
        sentence_end = SENTENCE_BOUNDARY.search(query, match.end())
        clause = query[match.end():sentence_end.start() if sentence_end else len(query)]
        if re.search(r"(?:필요(?:는|가)?\s*없|상관\s*없|싫)", clause[:25]):
            continue
        _set_preference(intent, "distance_m", "minimize")
        return


def _prune_explicit_nonrequests(query: str, intent: ParsedRouteIntent) -> None:
    """Use the last explicit mention to honor a later allowance or cancellation."""
    mentions = {
        factor: list(pattern.finditer(query))
        for factor, pattern in FACTOR_MENTIONS.items()
    }
    for preference in list(intent.preferences):
        occurrences = mentions.get(preference.factor, [])
        if not occurrences:
            continue
        mention = occurrences[-1]
        next_factor = min(
            (
                item.start()
                for factor, matches in mentions.items()
                if factor != preference.factor
                for item in matches
                if item.start() >= mention.end()
            ),
            default=len(query),
        )
        tail = query[mention.end():next_factor]
        sentence_end = re.search(r"[.!?]", tail)
        if sentence_end:
            tail = tail[:sentence_end.start()]
        tail = tail[:40]
        if _is_nonrequest_tail(preference.factor, tail) or REJECTED_COMPARISON_TAIL.search(tail):
            _drop_preference(intent, preference.factor)


def _prune_comparison_antecedents(query: str, intent: ParsedRouteIntent) -> None:
    """In 'A보다 B', discard an A-only factor, keeping requests restated in B."""
    for comparison in REJECTED_COMPARISON_TAIL.finditer(query):
        previous_boundary = list(SENTENCE_BOUNDARY.finditer(query, 0, comparison.start()))
        left_start = previous_boundary[-1].end() if previous_boundary else 0
        following_boundary = SENTENCE_BOUNDARY.search(query, comparison.end())
        right_end = following_boundary.start() if following_boundary else len(query)
        rejected = query[left_start:comparison.start()]
        chosen = query[comparison.end():right_end]
        if not any(pattern.search(chosen) for pattern in FACTOR_MENTIONS.values()):
            continue
        for preference in list(intent.preferences):
            pattern = FACTOR_MENTIONS.get(preference.factor)
            if pattern and pattern.search(rejected) and not pattern.search(chosen):
                _drop_preference(intent, preference.factor)


def _latest_correction_clause(query: str) -> str | None:
    cues = list(CORRECTION_CUE.finditer(query))
    return query[cues[-1].end():] if cues else None


def _apply_explicit_correction(query: str, intent: ParsedRouteIntent) -> None:
    """Reconcile the final, explicit correction across known route factors."""
    clause = _latest_correction_clause(query)
    if clause is None:
        return
    mentions = sorted(
        (match.start(), match.end(), factor)
        for factor, pattern in FACTOR_MENTIONS.items()
        for match in pattern.finditer(clause)
    )
    for index, (_, end, factor) in enumerate(mentions):
        next_start = mentions[index + 1][0] if index + 1 < len(mentions) else len(clause)
        tail = clause[end:next_start][:40]
        if _is_nonrequest_tail(factor, tail):
            _drop_preference(intent, factor)
        elif factor in {"stairs_distance_m", "crosswalk_count"}:
            if re.search(r"피하(?!지|진)|피해|없(?:는|이)|빼고", tail):
                _set_preference(intent, factor, "avoid")
            elif re.search(r"적게|적은|적으면|덜|최소", tail):
                _set_preference(intent, factor, "minimize")
        elif factor == "max_slope_percent" and re.search(r"낮|완만|적|평탄", tail):
            _set_preference(intent, factor, "minimize")
        elif re.search(r"많|밝|높|우선", tail):
            _set_preference(intent, factor, "maximize")
    # A correction can refer back to the previous factor without repeating it:
    # "횡단보도 없는 길로. 다시 말하면 없는 건 아니고 적게 건너면 돼".
    antecedent = clause[:mentions[0][0]] if mentions else clause
    if antecedent:
        previous = sorted(
            (match.start(), factor)
            for factor in ("stairs_distance_m", "crosswalk_count")
            for match in FACTOR_MENTIONS[factor].finditer(query[:len(query) - len(clause)])
        )
        if previous:
            factor = previous[-1][1]
            if re.search(r"적게|적으면|덜|최소", antecedent):
                _set_preference(intent, factor, "minimize")
            elif factor == "crosswalk_count" and re.search(
                r"(?:건너도|거쳐도).{0,10}(?:괜찮|상관\s*없|무방|돼|되)",
                antecedent,
            ):
                _drop_preference(intent, factor)
            elif factor == "stairs_distance_m" and re.search(
                r"(?:있어도|지나도|지나가도).{0,10}(?:괜찮|상관\s*없|무방|돼|되)",
                antecedent,
            ):
                _drop_preference(intent, factor)


def _preserve_unsupported_requests(query: str, intent: ParsedRouteIntent) -> None:
    """Canonicalize explicit unmet needs without replacing them with a different metric."""
    if "유모차" in query and re.search(r"유모차.{0,12}(?:다닐|통행|갈\s*수|이동)", query):
        _drop_preference(intent, "wheelchair_accessibility")
        _set_preference(intent, "stroller_accessibility", "maximize")
    if "엘리베이터" in query and re.search(r"엘리베이터.{0,12}(?:있|이용|탈)", query):
        for item in list(intent.preferences):
            if item.factor.startswith("elevator_"):
                _drop_preference(intent, item.factor)
        _set_preference(intent, "elevator_accessibility", "maximize")
    if re.search(r"사람(?:이)?\s*(?:덜|적게)\s*붐비", query) and not re.search(r"교통|차량", query):
        _drop_preference(intent, "traffic_congestion")
        _set_preference(intent, "crowd_density", "minimize")


def _preserve_mentioned_places(query: str, intent: ParsedRouteIntent) -> None:
    """A place name invented by the model cannot be sent to the resolver."""
    compact_query = re.sub(r"\s+", "", query).lower()
    for field in ("origin_name", "destination_name"):
        name = getattr(intent, field)
        if name:
            name = name.strip()
            if field == "destination_name":
                for particle in ("으로", "로"):
                    if (name.endswith(particle) and len(name) > len(particle)
                        and re.search(re.escape(name) + r"\s+(?:갈|가고|이동)", query)):
                        name = name[:-len(particle)]
                        break
            for suffix in ("까지", "에서", "부터"):
                if name.endswith(suffix) and len(name) > len(suffix):
                    name = name[:-len(suffix)]
                    break
            if name in {
                "까지", "에서", "부터", "출발", "도착",
                "출발지", "목적지", "미정", "여기", "거기",
            }:
                name = None
            setattr(intent, field, name)
        if name and re.sub(r"\s+", "", name).lower() not in compact_query:
            setattr(intent, field, None)
    # A model can copy the only mentioned destination into both slots.
    has_origin_marker = bool(re.search(r"에서|부터|출발", query))
    has_destination_marker = bool(re.search(r"까지|도착|으로", query))
    if has_destination_marker and not has_origin_marker:
        intent.origin_name = None
        if intent.destination_name is None:
            # One-sided requests of the form "도화초등학교까지 ..." have one
            # explicit name; recover that literal span rather than invent a start.
            leading_destination = re.match(
                r"^\s*([^\s,]+?)(?:까지(?:\s|$)|(?:으로|로)\s+(?:갈|가고|이동))",
                query,
            )
            if leading_destination:
                intent.destination_name = leading_destination.group(1)
    elif (
        has_origin_marker and not has_destination_marker
        and intent.origin_name == intent.destination_name
    ):
        intent.destination_name = None
    if re.search(r"출발지(?:는|가)?\s*(?:아직\s*)?(?:정하지|미정|몰라|모르)", query):
        intent.origin_name = None
    if re.search(r"(?:도착지|목적지)(?:는|가)?\s*(?:아직\s*)?(?:정하지|미정|몰라|모르)", query):
        intent.destination_name = None


def _period_hour_mentions(query: str) -> list[tuple[re.Match[str], str]]:
    matches = list(EXPLICIT_PERIOD_HOUR_PATTERN.finditer(query))
    mentions = []
    for index, match in enumerate(matches):
        following = query[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(query)]
        preceding = query[max(0, match.start() - 12):match.start()]
        if ARRIVAL_AFTER_TIME.search(following) or ARRIVAL_BEFORE_TIME.search(preceding):
            role = "arrival"
        elif DEPARTURE_AFTER_TIME.search(following) or DEPARTURE_BEFORE_TIME.search(preceding):
            role = "departure"
        else:
            role = "unspecified"
        mentions.append((match, role))
    return mentions


def _corrects_previous_clock(
    query: str, previous: re.Match[str], current: re.Match[str]
) -> bool:
    between = query[previous.end():current.start()]
    following = query[current.end():].split(".", 1)[0][:30]
    return bool(
        TIME_CORRECTION.search(between)
        or re.match(r"^\s*(?:로|으로|에)\s*(?:바꾸|바꿔|바꿨|변경|정정)", following)
    )


def _arrival_time_only(query: str) -> bool:
    query = _clock_text(query)
    mentions = _period_hour_mentions(query)
    if not mentions or len(EXPLICIT_TIME_PATTERN.findall(query)) != len(mentions):
        return False
    if all(role == "arrival" for _, role in mentions):
        return True
    return (
        len(mentions) > 1
        and all(role == "arrival" for _, role in mentions[:-1])
        and mentions[-1][1] == "unspecified"
        and _corrects_previous_clock(query, mentions[-2][0], mentions[-1][0])
    )


def _unambiguous_departure_clock(query: str) -> time | None:
    """Correct only a clear departure time, not an arrival deadline."""
    query = _clock_text(query)
    mentions = _period_hour_mentions(query)
    if len(EXPLICIT_TIME_PATTERN.findall(query)) != len(mentions):
        # An unqualified additional clock may be the user's correction.
        return None
    if _arrival_time_only(query):
        return None
    departure = [match for match, role in mentions if role == "departure"]
    candidates = [match for match, role in mentions if role != "arrival"]
    if len(mentions) > 1 and mentions[-1][1] != "arrival" and _corrects_previous_clock(
        query, mentions[-2][0], mentions[-1][0]
    ):
        selected = mentions[-1][0]
    elif len(departure) == 1:
        selected = departure[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        return None
    period, raw_hour, raw_minute, half_hour = selected.groups()
    hour = int(raw_hour)
    minute = 30 if half_hour else (int(raw_minute) if raw_minute is not None else 0)
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return None
    if period in {"오전", "새벽", "아침"}:
        expected_hour = 0 if hour == 12 else hour
    else:
        expected_hour = 0 if period == "밤" and hour == 12 else (hour + 12 if hour < 12 else 12)
    return time(expected_hour, minute)


def _discard_invented_time(query: str, intent: ParsedRouteIntent) -> None:
    """A vague daypart or an arrival-only deadline is not a departure time."""
    query = _clock_text(query)
    if intent.departure_time is not None and (
        not (EXPLICIT_TIME_PATTERN.search(query) or re.search(r"자정|정오", query))
        or _arrival_time_only(query)
    ):
        intent.departure_time = None


def _correct_explicit_departure_time(query: str, intent: ParsedRouteIntent) -> None:
    """Normalize an unambiguous departure clock after LLM extraction."""
    expected = _unambiguous_departure_clock(query)
    if intent.departure_time is not None and expected is not None:
        intent.departure_time = expected


def _discard_deadline_inferred_distance(query: str, intent: ParsedRouteIntent) -> None:
    """An arrival deadline alone does not request the shortest route."""
    if not any(role == "arrival" for _, role in _period_hour_mentions(_clock_text(query))):
        return
    if (
        EXPLICIT_SHORT_ROUTE.search(query)
        or AVOID_DETOUR.search(query)
        or re.search(r"빠른\s*(?:길|경로)|빨리\s*(?:가|도착|걷)|거리\s*(?:짧|최소)", query)
    ):
        return
    _drop_preference(intent, "distance_m")


def _preserve_explicit_no_stairs(query: str, intent: ParsedRouteIntent) -> None:
    """Keep an unambiguous safety constraint even when the model omits it."""
    scope = _last_factor_scope(query, "stairs_distance_m")
    if STAIRS_DISCLAIMER.search(scope):
        return
    if not re.search(
        r"계단(?:이|은|는|을|를|가)?\s*(?:하나도\s*)?(?:없는|없이|없게|피하(?!지|진)|피해|빼고)",
        scope,
    ):
        return
    _set_preference(intent, "stairs_distance_m", "avoid")


def _preserve_crossing_preference(query: str, intent: ParsedRouteIntent) -> None:
    if CROSSING_DISCLAIMER.search(query):
        return
    match = re.search(
        r"(?:건널목|횡단보도)(?:은|는|을|를|가|이)?\s*"
        r"(없이|없는|적게|적은|덜|최소|회피|피해|피하(?!지|진)|가급적\s*피하)",
        query,
    )
    if not match:
        return
    direction = "avoid" if match.group(1) in {"없이", "없는"} else "minimize"
    _set_preference(intent, "crosswalk_count", direction)


def _preserve_explicit_flat_ground(query: str, intent: ParsedRouteIntent) -> None:
    """Retain an explicit flat-ground request if the small model drops it."""
    if "평지" not in query or FLAT_DISCLAIMER.search(query):
        return
    _set_preference(intent, "max_slope_percent", "minimize")


def _validate_query_semantics(query: str, intent: ParsedRouteIntent) -> None:
    if EXPLICIT_TIME_PATTERN.search(_clock_text(query)) and not _arrival_time_only(query) and intent.departure_time is None:
        raise ValueError("An explicit departure time was omitted")
    expected_clock = _unambiguous_departure_clock(query)
    if expected_clock is not None and intent.departure_time is not None:
        if intent.departure_time != expected_clock:
            raise ValueError("Explicit hour was not converted to 24-hour time")
    if ROUTE_PLACE_PATTERN.search(query) and (
        intent.origin_name is None or intent.destination_name is None
    ):
        raise ValueError("An explicit origin or destination was omitted")
    if re.search(r"\S{2,}\s*까지", query) and intent.destination_name is None:
        raise ValueError("An explicit destination was omitted")
    factors = {preference.factor: preference.direction for preference in intent.preferences}
    stairs_scope = _last_factor_scope(query, "stairs_distance_m")
    if re.search(
        r"계단(?:이|은|는|을|를|가)?\s*(?:하나도\s*)?(?:없는|없이|없게|피하(?!지|진)|피해|빼고)",
        stairs_scope,
    ) and not STAIRS_DISCLAIMER.search(stairs_scope) and factors.get(
        "stairs_distance_m"
    ) != "avoid":
        raise ValueError("An explicit no-stairs constraint was not preserved")
    if "평지" in query and not FLAT_DISCLAIMER.search(query) and "flatness" in factors:
        raise ValueError("flatness duplicates the mapped max_slope_percent factor")


def _discard_unmentioned_distance(query: str, intent: ParsedRouteIntent) -> None:
    """Keep backend defaults separate from preferences actually requested.

    Only prune an invented distance preference when no distance/urgency wording
    exists; do not fabricate positive conditions from bare facility names.
    """
    if not re.search(r"거리|최단|짧|가까|가깝|멀|먼|길게|긴\s*(?:길|경로)|빠르|빠른|빠르게|빨리|신속|서둘|급하|급해|우회|돌아", query):
        _drop_preference(intent, "distance_m")


def _request_ollama(payload: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LocalLLMUnavailableError(
            "GPU 모델 서버 연결 또는 응답에 실패했습니다. SSH 터널 창과 서버 상태를 확인한 뒤 다시 검색해 주세요."
        ) from exc
    if not isinstance(data, dict):
        raise LocalLLMOutputError("Ollama returned an invalid response envelope")
    return data


def parse_route_intent(query: str) -> ParsedRouteIntent:
    settings = get_settings()
    query = query.strip()
    key = (settings.ollama_base_url, settings.ollama_model, SYSTEM_PROMPT, query)
    if settings.ollama_intent_cache_seconds > 0:
        with _intent_cache_lock:
            now = monotonic()
            for expired in [k for k, (until, _) in _intent_cache.items() if until <= now]:
                del _intent_cache[expired]
            cached = _intent_cache.get(key)
            if cached is not None:
                _intent_cache.move_to_end(key)
                logger.info("route_intent cache_hit=true")
                # Deserialize a fresh value: downstream code must not mutate the cache.
                return ParsedRouteIntent.model_validate_json(cached[1])
    started = monotonic()
    intent = _parse_route_intent_uncached(query)
    if settings.ollama_intent_cache_seconds > 0:
        with _intent_cache_lock:
            _intent_cache[key] = (
                monotonic() + settings.ollama_intent_cache_seconds,
                intent.model_dump_json(),
            )
            _intent_cache.move_to_end(key)
            while len(_intent_cache) > _INTENT_CACHE_MAX_SIZE:
                _intent_cache.popitem(last=False)
    logger.info("route_intent cache_hit=false seconds=%.3f", monotonic() - started)
    return intent


def _parse_route_intent_uncached(query: str) -> ParsedRouteIntent:
    settings = get_settings()
    payload: dict[str, object] = {
        "model": settings.ollama_model,
        "stream": False,
        "think": False,
        "keep_alive": settings.ollama_keep_alive,
        "format": ParsedRouteIntent.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    }
    last_error: ValidationError | json.JSONDecodeError | ValueError | None = None
    for attempt in range(2):
        data = _request_ollama(payload)
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LocalLLMOutputError("Ollama response has no message content")
        try:
            intent = ParsedRouteIntent.model_validate_json(content)
            _discard_invented_time(query, intent)
            _correct_explicit_departure_time(query, intent)
            _reconcile_disclaimed_preferences(query, intent)
            _normalize_explicit_route_preferences(query, intent)
            _preserve_explicit_short_route(query, intent)
            _discard_deadline_inferred_distance(query, intent)
            _preserve_unsupported_requests(query, intent)
            _preserve_explicit_no_stairs(query, intent)
            _preserve_crossing_preference(query, intent)
            _preserve_explicit_flat_ground(query, intent)
            if AVOID_DARK_ROAD.search(query):
                _set_preference(intent, "streetlight_score", "maximize")
            if AVOID_DETOUR.search(query):
                _set_preference(intent, "distance_m", "minimize")
            _preserve_mentioned_places(query, intent)
            _prune_explicit_nonrequests(query, intent)
            _prune_comparison_antecedents(query, intent)
            _apply_explicit_correction(query, intent)
            _discard_unmentioned_distance(query, intent)
            _validate_query_semantics(query, intent)
            return intent
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                payload["messages"] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"이전 JSON이 의미 검증에 실패했다: {exc}. 한 번만 수정하라. "
                            "문장에 명시된 시각은 departure_time에만 넣고, 요청 필드는 "
                            "preference factor가 아니다. 출발지와 도착지도 누락하지 말고, "
                            "실제 언급된 장소만 채우고 없는 출발지/도착지는 null로 둔다. "
                            "'까지' 자체는 장소명이 아니다. 사용자가 말한 조건을 모두 보존하라. "
                            "밤 11시는 23:00:00, 오전 12시는 00:00:00이다. "
                            "평지는 max_slope_percent/minimize이며 flatness는 추가하지 않는다. "
                            "CCTV가 명시됐으면 cctv_score를 빠뜨리지 않는다. "
                            "수정된 JSON만 반환하라."
                        ),
                    },
                ]
    raise LocalLLMOutputError(
        "Local model output did not match the route intent schema"
    ) from last_error
