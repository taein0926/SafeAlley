import json
import re

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.agent import ParsedRouteIntent


class LocalLLMUnavailableError(RuntimeError):
    """Raised when the configured local Ollama service cannot be reached."""


class LocalLLMOutputError(RuntimeError):
    """Raised when the model response does not satisfy the structured schema."""


SYSTEM_PROMPT = """한국어 보행 경로 요청을 제공된 스키마의 JSON으로 구조화한다.
JSON 외의 설명을 출력하지 않는다. 좌표, SQL, Tool 이름을 만들지 않는다.

규칙:
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
  횡단보도 수=crosswalk_count, 계단=stairs, 경사=slope,
  경찰서/도움시설 접근성=police_accessibility.
- 적게/낮게/짧게는 minimize, 많게/밝게/안전하게는 maximize,
  명시적으로 피하라고 한 경우만 avoid이다.
- weight는 0.1부터 100까지의 상대 중요도다. 중요도를 따로 말하지 않으면 1이다.
- 사용자가 요청하지 않은 조건은 만들지 않는다.

예시:
사용자: 밤 10시에 가로등과 CCTV가 많은 길로 안내해줘
출력: {"departure_time":"22:00:00","profile":"pedestrian","preferences":[{"factor":"streetlight_score","direction":"maximize","weight":1},{"factor":"cctv_score","direction":"maximize","weight":1}]}
사용자: 가장 짧은 길로 안내해줘
출력: {"departure_time":null,"profile":"pedestrian","preferences":[{"factor":"distance_m","direction":"minimize","weight":1}]}
"""


EXPLICIT_TIME_PATTERN = re.compile(
    r"(?:(?:오전|오후|밤|새벽)\s*)?\d{1,2}\s*(?:시|:\s*\d{2})"
)


def _validate_query_semantics(query: str, intent: ParsedRouteIntent) -> None:
    if EXPLICIT_TIME_PATTERN.search(query) and intent.departure_time is None:
        raise ValueError("An explicit departure time was omitted")


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
                            "이전 JSON이 의미 검증에 실패했다. 한 번만 수정하라. "
                            "문장에 명시된 시각은 departure_time에만 넣고, 요청 필드는 "
                            "preference factor가 아니며, 사용자가 말한 조건을 누락하지 마라. "
                            "수정된 JSON만 반환하라."
                        ),
                    },
                ]
    raise LocalLLMOutputError(
        "Local model output did not match the route intent schema"
    ) from last_error
