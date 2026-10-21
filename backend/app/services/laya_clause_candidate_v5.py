"""Pilot-only low-light avoidance polarity and unfinished-tail guard.

The model and earlier policies remain frozen. Never treat the prefix of
안내 as the separate negation 안; never infer avoidance from an unfinished 피.
"""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.incomplete_conditions import preview_factor_evidence
from app.services.laya_clause_candidate_v2 import _EXPLANATION, _MOVEMENT

_NOUN = re.compile(r'(?<![가-힣])(?:가로등|조명)(?![가-힣])|(?<![가-힣])(?:가로등|조명)(?=은|는|이|가)')
_LOW = re.compile(r'(?<![가-힣])(?:가로등|조명)(?:은|는|이|가)?\s*(?:적은|없는|부족한)\s*(?:곳|구간|길|경로)(?:은|는|을|를)?\s*')
_NEGATIVE = re.compile(r'^(?:피하지\s*않아도\s*(?:돼|되)|피하고\s*싶지\s*않|피해서\s*(?:가지\s*마|가고\s*싶지|안(?:\s|가|갈|걷)))')
_POSITIVE = re.compile(r'^(?:피해서(?=\s|$)|피해(?:줘|주세요)(?=\s|[.!?]|$)|피하고\s*싶(?:어요|습니다|어)(?=\s|[.!?]|$))')
_PARTIAL = re.compile(r'^(?:피|피하|피해|피하지|피하고|피하고\s*싶|피하고\s*싶지)\s*$')


def refine_clause_cards_v5(body, query, cards):
    if _EXPLANATION.search(query) and not _MOVEMENT.search(query):
        return cards
    lighting_mentions = list(_NOUN.finditer(query))
    if not lighting_mentions:
        return cards
    chosen = None
    for match in _LOW.finditer(query):
        # Do not supersede a later explicit lighting condition/cancellation.
        if match.start() != lighting_mentions[-1].start():
            continue
        tail = query[match.end():]
        if _NEGATIVE.match(tail):
            chosen = ConditionCard(factor='streetlight', state='not_applied', judgment='skip', confidence=None,
                reason='가로등이 적은 곳을 피할 필요가 없다는 표현을 우선 요청으로 확대하지 않았습니다.')
        elif _PARTIAL.fullmatch(tail):
            chosen = ConditionCard(factor='streetlight', state='analyzing', judgment='pending', confidence=None,
                reason='가로등이 적은 곳에 대한 회피 표현이 아직 끝나지 않았습니다.')
        elif _POSITIVE.match(tail):
            projected = query[:match.start()] + '가로등이 많은 길로 안내해줘 ' + tail
            if preview_factor_evidence(projected, 'streetlight') == ('positive', 'apply'):
                chosen = ConditionCard(factor='streetlight', state='applied', judgment='apply', direction='maximize', confidence=None,
                    reason='가로등이 적은 구간을 피하려는 완료된 요청을 반영했습니다.')
    return [chosen if c.factor == 'streetlight' and chosen is not None else c for c in cards]
