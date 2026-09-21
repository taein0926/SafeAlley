import json
import re
from datetime import time

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.agent import ParsedRouteIntent, RoutePreference


class LocalLLMUnavailableError(RuntimeError):
    """Raised when the configured local Ollama service cannot be reached."""


class LocalLLMOutputError(RuntimeError):
    """Raised when the model response does not satisfy the structured schema."""


SYSTEM_PROMPT = """한국어 보행 경로 요청을 제공된 스키마의 JSON으로 구조화한다.
JSON 외의 설명을 출력하지 않는다. 좌표, SQL, Tool 이름을 만들지 않는다.

규칙:
- 출발 장소는 origin_name, 도착 장소는 destination_name에 사용자가 말한 이름 그대로 넣는다.
- 장소가 문장에 없을 때만 해당 장소명은 null이다. 장소를 추측하거나 만들지 않는다.
- profile은 항상 \"pedestrian\"이다.
- 문장에 시각이 있으면 반드시 departure_time에 24시간제로 넣는다.
  밤 10시는 \"22:00:00\", 오전 6시 30분은 \"06:30:00\"이다.
  날짜가 없는 현지 시각이므로 Z나 시간대 오프셋을 붙이지 않는다.
  시각이 없을 때만 null이다. 시간은 preference가 아니며 departure_time을
  factor에 절대 넣지 않는다.
- 사용자가 말한 모든 경로 조건을 preferences에 보존하고 다른 조건으로 바꾸지 않는다.
- 검증된 factor 매핑은 다음과 같다.
  거리/최단거리=distance_m, 안전=safety_score,
  가로등/조명=streetlight_score, CCTV=cctv_score.
- 아직 지원되지 않는 조건도 버리지 말고 snake_case factor로 보존한다.
  횡단보도 수=crosswalk_count, 계단=stairs_distance_m,
  보도/보행공간=sidewalk_coverage_percent, 경사=max_slope_percent,
  경찰서/도움시설 접근성=police_accessibility.
  평지/완만한 길/오르막이 적은 길=max_slope_percent(minimize)이다.
  flatness 같은 새 factor를 만들지 않는다.
- 적게/낮게/짧게는 minimize, 많게/밝게/안전하게는 maximize,
  피하라/없는 길/없이/안 지나는 길은 avoid이다.
  "계단이 적은 길"은 minimize이고 "계단 없이"는 avoid이다.
- 서로 다른 시설·지표가 한 문장에 나오면 각각 바로 인접한 수식어로 방향을 정한다.
  "횡단보도는 적고 CCTV가 많은"은 횡단보도 minimize, CCTV maximize이다.
- weight는 0.1부터 100까지의 상대 중요도다. 중요도를 따로 말하지 않으면 1이다.
- 사용자가 요청하지 않은 조건은 만들지 않는다.

예시:
사용자: 밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘
출력: {"origin_name":"주안역","destination_name":"인천사랑병원","departure_time":"22:00:00","profile":"pedestrian","preferences":[{"factor":"cctv_score","direction":"maximize","weight":1}]}
사용자: 가장 짧은 길로 안내해줘
출력: {"origin_name":null,"destination_name":null,"departure_time":null,"profile":"pedestrian","preferences":[{"factor":"distance_m","direction":"minimize","weight":1}]}
사용자: 밤 10시에 주안역에서 인천사랑병원까지 계단 없이 가로등과 CCTV가 많은 길로 안내해줘
출력: {"origin_name":"주안역","destination_name":"인천사랑병원","departure_time":"22:00:00","profile":"pedestrian","preferences":[{"factor":"stairs_distance_m","direction":"avoid","weight":1},{"factor":"streetlight_score","direction":"maximize","weight":1},{"factor":"cctv_score","direction":"maximize","weight":1}]}
사용자: 횡단보도는 되도록 적고 CCTV가 많은 길로 안내해줘
출력: {"origin_name":null,"destination_name":null,"departure_time":null,"profile":"pedestrian","preferences":[{"factor":"crosswalk_count","direction":"minimize","weight":1},{"factor":"cctv_score","direction":"maximize","weight":1}]}
"""


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
    payload: dict[str, object] = {
        "model": settings.ollama_model,
        "stream": False,
        "think": False,
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
