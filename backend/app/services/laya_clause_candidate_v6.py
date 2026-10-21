"""Final pilot guard: preserve explanation rejection and complete permissions.

No model calls or learning. Earlier policies stay intact for paired replay.
"""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.laya_clause_candidate_v2 import _EXPLANATION, _MOVEMENT
from app.services.laya_clause_candidate_v5 import _LOW, _NOUN

_ALLOW_LOW_LIGHT = re.compile(
    r'^피하지\s*않아도\s*(?:됩니다|됩니다만|괜찮|상관\s*없|무방)'
)


def refine_clause_cards_v6(body, query, cards):
    # Earlier positive recovery must not undo the existing non-navigation
    # explanation guard. Use its original definition, not a new broad intent.
    if _EXPLANATION.search(query) and not _MOVEMENT.search(query):
        return [ConditionCard(factor=c.factor,state='not_applied',judgment='skip',confidence=None,
            reason='이동 요청이 아닌 용어 설명 질문이므로 조건을 적용하지 않았습니다.') for c in cards]
    mentions=list(_NOUN.finditer(query))
    if not mentions:
        return cards
    for match in _LOW.finditer(query):
        if match.start()==mentions[-1].start() and _ALLOW_LOW_LIGHT.match(query[match.end():]):
            return [ConditionCard(factor='streetlight',state='not_applied',judgment='skip',confidence=None,
                reason='가로등이 적은 곳을 허용하는 완료된 표현을 선호 요청으로 확대하지 않았습니다.')
                if c.factor=='streetlight' else c for c in cards]
    return cards
