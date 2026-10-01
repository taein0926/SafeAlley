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
시각=departure_time(HH:MM:SS, 시간대 없음). 밤 10시=22:00:00, 오전 6시30분=06:30:00.
시각이 없으면 departure_time은 반드시 null이다. 00:00:00이나 현재 시각을 만들어 넣지 않는다.
조건은 preferences의 factor/direction으로 모두 보존한다. 요청하지 않은 조건은 만들지 않는다.
factor: 최단/거리=distance_m, 안전=safety_score, 조명/가로등=streetlight_score,
CCTV=cctv_score, 건널목/횡단보도=crosswalk_count, 계단=stairs_distance_m,
보도/인도=sidewalk_coverage_percent,
경사/평지/완만한 길=max_slope_percent, 경찰서 접근성=police_accessibility.
미지원 조건도 snake_case factor로 보존한다. flatness는 쓰지 않는다.
direction: 적게/짧게/평지=minimize, 많게/밝게/안전하게=maximize, 없이/피해/없는 길=avoid.
각 조건에 인접한 수식어를 적용: 횡단보도는 적고 CCTV가 많은=각각 minimize, maximize.
계단 적게=minimize, 계단 없이=avoid. 건널목/횡단보도 회피·가급적 피해=minimize,
건널목/횡단보도 없이·절대 건너지 않기=avoid. 여기서 건널목은 철도가 아닌 보행 횡단보도다.
시간/장소/profile은 factor가 아니다.
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


EXPLICIT_TIME_PATTERN = re.compile(
    r"(?:(?:오전|오후|밤|새벽)\s*)?\d{1,2}\s*(?:시|:\s*\d{2})"
)
NIGHT_HOUR_PATTERN = re.compile(r"(밤|오후)\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?")
ROUTE_PLACE_PATTERN = re.compile(r"\S.+?에서\s+\S.+?까지")


def _correct_explicit_pm_time(query: str, intent: ParsedRouteIntent) -> None:
    """Normalize one unambiguous clock phrase after LLM extraction."""
    matches = list(NIGHT_HOUR_PATTERN.finditer(query))
    if intent.departure_time is None or len(matches) != 1:
        return
    if len(EXPLICIT_TIME_PATTERN.findall(query)) != 1:
        return
    period, raw_hour, raw_minute = matches[0].groups()
    hour = int(raw_hour)
    minute = int(raw_minute) if raw_minute is not None else 0
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return
    expected_hour = 0 if period == "밤" and hour == 12 else (hour + 12 if hour < 12 else 12)
    intent.departure_time = time(expected_hour, minute)


def _preserve_explicit_no_stairs(query: str, intent: ParsedRouteIntent) -> None:
    """Keep an unambiguous safety constraint even when the model omits it."""
    if not re.search(r"계단(?:이|은)?\s*(?:없는|없이|피하)", query):
        return
    for preference in intent.preferences:
        if preference.factor == "stairs_distance_m":
            preference.direction = "avoid"
            return
    if len(intent.preferences) < 20:
        intent.preferences.append(
            RoutePreference(factor="stairs_distance_m", direction="avoid", weight=1)
        )


def _preserve_crossing_preference(query: str, intent: ParsedRouteIntent) -> None:
    match = re.search(r"(?:건널목|횡단보도)(?:은|는|을|를|가|이)?\s*(없이|없는|적게|적은|덜|최소|회피|피해|피하|가급적)", query)
    if not match:
        return
    direction = "avoid" if match.group(1) in {"없이", "없는"} else "minimize"
    for preference in intent.preferences:
        if preference.factor == "crosswalk_count":
            preference.direction = direction
            return
    if len(intent.preferences) < 20:
        intent.preferences.append(RoutePreference(factor="crosswalk_count", direction=direction))


def _preserve_explicit_flat_ground(query: str, intent: ParsedRouteIntent) -> None:
    """Retain an explicit flat-ground request if the small model drops it."""
    if "평지" not in query:
        return
    for preference in intent.preferences:
        if preference.factor == "max_slope_percent":
            preference.direction = "minimize"
            return
    if len(intent.preferences) < 20:
        intent.preferences.append(
            RoutePreference(factor="max_slope_percent", direction="minimize", weight=1)
        )


def _validate_query_semantics(query: str, intent: ParsedRouteIntent) -> None:
    if EXPLICIT_TIME_PATTERN.search(query) and intent.departure_time is None:
        raise ValueError("An explicit departure time was omitted")
    night_hour = NIGHT_HOUR_PATTERN.search(query)
    if night_hour and intent.departure_time is not None:
        hour = int(night_hour.group(2))
        expected = 0 if night_hour.group(1) == "밤" and hour == 12 else (
            hour + 12 if 1 <= hour <= 11 else hour
        )
        if intent.departure_time.hour != expected:
            raise ValueError("PM hour was not converted to 24-hour time")
    if ROUTE_PLACE_PATTERN.search(query) and (
        intent.origin_name is None or intent.destination_name is None
    ):
        raise ValueError("An explicit origin or destination was omitted")
    factors = {preference.factor: preference.direction for preference in intent.preferences}
    if re.search(r"계단(?:이|은)?\s*(?:없는|없이|피하)", query) and factors.get(
        "stairs_distance_m"
    ) != "avoid":
        raise ValueError("An explicit no-stairs constraint was not preserved")
    if "평지" in query and factors.get("max_slope_percent") != "minimize":
        raise ValueError("A flat-ground preference was not mapped to slope")
    if "평지" in query and "flatness" in factors:
        raise ValueError("flatness duplicates the mapped max_slope_percent factor")
    if "CCTV" in query.upper() and "cctv_score" not in factors:
        raise ValueError("An explicit CCTV preference was omitted")


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
        raise LocalLLMUnavailableError("Local Ollama service is unavailable") from exc
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
            _correct_explicit_pm_time(query, intent)
            _preserve_explicit_no_stairs(query, intent)
            _preserve_crossing_preference(query, intent)
            _preserve_explicit_flat_ground(query, intent)
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
                            "사용자가 말한 조건을 모두 보존하라. 밤 11시는 23:00:00이다. "
                            "평지는 max_slope_percent/minimize이며 flatness는 추가하지 않는다. "
                            "CCTV가 명시됐으면 cctv_score를 빠뜨리지 않는다. "
                            "수정된 JSON만 반환하라."
                        ),
                    },
                ]
    raise LocalLLMOutputError(
        "Local model output did not match the route intent schema"
    ) from last_error
