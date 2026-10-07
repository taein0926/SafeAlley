"""Paid Jev judgments for input previews only; never executes a routing tool."""

import math
from collections import OrderedDict
from threading import Lock
from time import monotonic

import httpx

from app.core.config import get_settings
from app.schemas.intent_preview import CARD_ORDER, ConditionCard, IntentPreviewResponse, IntentPreviewStatus

API_URL = "https://api.typesafe.ai/v1/systemone"
_lock = Lock()
_last_call = 0.0
_cache: OrderedDict = OrderedDict()
COMMON = (
    "사용자가 작성 중인 한국어 보행 요청의 전체 문장을 읽고, 이 항목만 판단한다. "
    "장소명에 포함된 단어를 조건으로 보지 않는다. 미지원 조건을 다른 조건으로 대체하지 않는다. "
    "원하는 조건, 허용하는 조건, 철회한 조건을 구분한다. 뒤에서 취소·수정한 요청을 우선한다. "
    "문장 전체가 미완성이어도 이 항목을 언급하지 않았다면 반드시 skip이다. "
    "pending은 이 항목을 막 입력했지만 선호 방향이 아직 불명확한 경우에만 고른다. "
    "항목별 근거를 독립적으로 판단하며 다른 항목이나 일반적인 보행 목적을 추론해 적용하지 않는다. "
)
QUESTIONS = {
    "distance": "출발지에서 목적지까지 최단거리·짧은 길을 명시적으로 우선하는가? 단순히 길을 안내해 달라는 요청이나 다른 시설·회피 조건만 있으면 skip이다. 보통 사람은 짧은 길을 원할 것이라는 상식으로 추론하지 않는다. 조금 멀어져도 괜찮다는 허용도 skip이다.",
    "safety": "사용자가 안전한 길 또는 안전시설 종합을 명시적으로 우선했는가? 가로등·CCTV·계단만 요청한 것을 종합 안전 요청으로 확대하지 않는다.",
    "streetlight": "가로등이 많거나 밝은 길을 우선하는가? 어두운 길 회피도 포함한다.",
    "cctv": "CCTV가 많거나 CCTV와 가까운 길을 우선하는가? 단순 목적지 이름은 제외한다.",
    "stairs": "계단을 아예 피하려는가, 적게 지나려는가? 계단이 있어도 괜찮거나 피하지 않아도 된다는 말은 skip이다.",
    "crossing": "건널목·횡단보도를 아예 피하려는가, 적게 지나려는가? 건너도 괜찮다는 말은 skip이다.",
    "bridge": "육교를 이용하고 싶은가, 아예 피하고 싶은가, 적게 지나고 싶은가? 육교가 있어도 괜찮다는 허용이나 계단 회피만으로 육교 조건을 추론하지 않는다. 육교가 포함된 목적지 이름은 제외한다.",
    "time": "출발 시각·시간대를 명시했는가? 밤·오전·오후와 시각을 함께 읽는다. 시각이 없으면 skip이다.",
}


class PreviewUnavailable(RuntimeError):
    pass


class PreviewLimited(PreviewUnavailable):
    pass


def reset_preview_state() -> None:
    global _last_call
    with _lock:
        _last_call = 0
        _cache.clear()


def preview_status() -> IntentPreviewStatus:
    settings = get_settings()
    configured = bool(settings.typesafe_api_key)
    return IntentPreviewStatus(enabled=settings.jev_preview_enabled, configured=configured,
                               available=settings.jev_preview_enabled and configured)


def build_request(query: str, model: str) -> dict:
    questions = {}
    for factor in CARD_ORDER:
        choices = {"apply": "이 조건을 분명히 원한다", "skip": "이 조건을 요청하지 않았거나 철회·허용했다", "pending": "문장이 미완성이라 아직 판단할 수 없다"}
        if factor in {"stairs", "crossing"}:
            choices = {"avoid": "해당 구간을 전혀 지나지 않는 길을 명시적으로 원한다",
                       "minimize": "적게 또는 가급적 피해서 지나고 싶지만 일부는 허용한다",
                       "skip": "요청하지 않았거나 피하지 않아도 된다", "pending": "미완성이라 방향을 정할 수 없다"}
        if factor == "time":
            choices = {"night": "명시된 출발 시간대가 밤·심야·새벽이다", "day": "명시된 출발 시간대가 낮이다",
                       "skip": "출발 시간대를 명시하지 않았다", "pending": "시간 표현이 미완성이거나 명확하지 않다"}
        if factor == "bridge":
            choices = {"apply": "육교를 이용하는 길을 명시적으로 원한다",
                       "avoid": "육교를 전혀 지나지 않는 길을 명시적으로 원한다",
                       "minimize": "육교를 적게 또는 가급적 피해서 지나고 싶다",
                       "skip": "육교 조건을 요청하지 않았거나 철회·허용했다", "pending": "미완성이라 방향을 정할 수 없다"}
        questions[factor] = {"type": "choice", "instructions": COMMON + QUESTIONS[factor], "criteria": choices}
    return {"state": query, "model": model, "questions": questions}


def parse_decisions(payload: dict, response: dict, minimum_confidence: float) -> list[ConditionCard]:
    """Project each independent Jev decision into its preview card."""
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise PreviewUnavailable("Jev 판단 응답 형식을 확인할 수 없습니다.")
    cards = []
    for factor in CARD_ORDER:
        answer = answers.get(factor)
        criteria = payload["questions"][factor]["criteria"]
        if not isinstance(answer, dict) or answer.get("type") != "choice" or answer.get("choice") not in criteria:
            raise PreviewUnavailable("Jev 조건별 판단값이 누락됐습니다.")
        confidence = answer.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise PreviewUnavailable("Jev 신뢰도 형식을 확인할 수 없습니다.")
        choice = answer["choice"]
        state = "analyzing" if choice == "pending" else "not_applied" if choice == "skip" or confidence < minimum_confidence else "applied"
        direction = None
        period = None
        if state == "applied":
            if factor == "time":
                period = choice
            else:
                direction = choice if choice in {"avoid", "minimize"} else "minimize" if factor == "distance" else "maximize"
        cards.append(ConditionCard(factor=factor, state=state, confidence=confidence, direction=direction, period=period, judgment=choice))
    return cards


def analyze_preview(query: str) -> IntentPreviewResponse:
    global _last_call
    settings = get_settings()
    if not settings.jev_preview_enabled or not settings.typesafe_api_key:
        raise PreviewUnavailable("실시간 조건 분석이 아직 연결되지 않았습니다.")
    query = query.strip()
    now = monotonic()
    key = (settings.jev_preview_model, settings.jev_preview_min_confidence, query)
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 60:
            _cache.move_to_end(key)
            return hit[1].model_copy(update={"cached": True})
        if now - _last_call < .75:
            raise PreviewLimited("입력 내용을 모으고 있습니다. 잠시 뒤 다시 입력해 주세요.")
        _last_call = now
    payload = build_request(query, settings.jev_preview_model)
    try:
        response = httpx.post(API_URL, json=payload,
                              headers={"Authorization": "Bearer " + settings.typesafe_api_key.get_secret_value()}, timeout=8)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        raise PreviewUnavailable(f"실시간 조건 분석 연결에 실패했습니다 (HTTP {exc.response.status_code}).") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise PreviewUnavailable("실시간 조건 분석 응답을 받지 못했습니다.") from exc
    if not isinstance(body, dict) or not isinstance(body.get("model"), str):
        raise PreviewUnavailable("Jev 모델 응답을 확인할 수 없습니다.")
    cards = parse_decisions(payload, body, settings.jev_preview_min_confidence)
    usage = body.get("usage", {})
    tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
    result = IntentPreviewResponse(query=query, model=body["model"], conditions=cards,
                                   input_tokens=tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else None)
    with _lock:
        _cache[key] = (monotonic(), result)
        if len(_cache) > 64:
            _cache.popitem(last=False)
    return result
