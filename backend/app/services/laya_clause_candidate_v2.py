"""Pilot-only candidate around already selected clause mapping. No model calls."""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.incomplete_conditions import preview_factor_evidence, _preview_scope

_EXPLANATION = re.compile(r'무슨\s*(?:뜻|의미)|(?:뜻|의미).{0,6}(?:설명|알려)|설명해|정의(?:가|를|는)')
_MOVEMENT = re.compile(r'안내해|추천해|찾아(?:줘|주세요)|가고\s*싶|갈래|출발|걷고\s*싶|가는\s*(?:길|경로).{0,8}알려')
_NOUNS = {
 'distance':r'최단거리|거리', 'safety':r'안전시설|도움시설|경찰서|지구대|파출소|소방서|응급실',
 'streetlight':r'가로등|조명', 'cctv':r'CCTV|씨씨티비|방범카메라',
 'stairs':r'계단|층계','crossing':r'횡단보도|건널목','bridge':r'육교|고가보도',
}
_OPEN_COORDINATION = {f:re.compile(r'(?<![가-힣])(?:'+n+r')(?:은|는|을|를|이|가|도)?\s*(?:와|과|및|하고|그리고|,)\s*$',re.I) for f,n in _NOUNS.items()}
_DIRECT_CANCEL = re.compile(r'^\s*(?:은|는|을|를|이|가|도)?\s*(?:빼고|제외해|고려하지\s*(?:마|말|않)|신경\s*쓰지\s*마|우선하지\s*마|필요(?:는|가)?\s*없)')


def refine_clause_cards_v2(body, query, cards):
    """Limit changes to non-navigation explanations, open lists, direct cancellation."""
    if _EXPLANATION.search(query) and not _MOVEMENT.search(query):
        return [ConditionCard(factor=c.factor,state='not_applied',judgment='skip',confidence=None,
            reason='이동 조건 요청이 아니라 용어 설명 질문입니다.') for c in cards]
    output=[]
    for card in cards:
        pattern=_OPEN_COORDINATION.get(card.factor)
        dangling=pattern.search(query) if pattern else None
        if dangling:
            # Do not erase an earlier completed request for the same factor.
            prior,_=preview_factor_evidence(query[:dangling.start()],card.factor)
            if prior!='positive':
                output.append(ConditionCard(factor=card.factor,state='analyzing',judgment='pending',confidence=None,
                    reason='조건 목록이 연결어에서 끝나 이어지는 입력을 기다립니다.'))
                continue
        if card.factor in {'distance','safety','streetlight','cctv'}:
            scope=_preview_scope(query,card.factor)
            if scope and _DIRECT_CANCEL.search(scope[1]) and preview_factor_evidence(query,card.factor)[0]=='negative':
                output.append(ConditionCard(factor=card.factor,state='not_applied',judgment='skip',confidence=None,
                    reason='마지막에 명시적으로 제외한 조건을 반영했습니다.'))
                continue
        output.append(card)
    return output
