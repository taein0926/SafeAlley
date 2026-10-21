"""Pilot-only clause candidate. Never changes model weights or Jev guards."""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.incomplete_conditions import preview_factor_evidence

_FACILITY_PROXIMITY = re.compile(
    r'(?<![가-힣])(?P<noun>경찰서|지구대|파출소|소방서|119\s*안전센터|응급실|응급의료기관)'
    r'(?P<particle>은|는|이|가|와|과|에)?\s*가깝(?=고|게|다면|기를)'
)
_LIGHT_CAMERA = r'(?:가로등|조명|CCTV|씨씨티비|방범카메라|감시카메라)'
_SHARED_MANY = re.compile(
    r'(?<![가-힣])(?P<nouns>'+_LIGHT_CAMERA+r'(?:\s*(?:과|와|및|하고|그리고|,)\s*'+_LIGHT_CAMERA+r')+)'
    r'(?:이|가|은|는)?\s*(?P<predicate>많고|많은|많으며|많으면|많았으면|많아야)(?=\s|[.!?,]|$)',
    re.IGNORECASE,
)
_ROUTE_REQUEST = re.compile(r'길|경로|안내|까지|가고|가줘|갈래|걷|찾아|추천')


def refine_clause_cards(body, query, cards):
    """Project only verified positive local clauses into existing evidence guard.

    Retain all negative/incomplete/absent decisions otherwise. No fabricated
    confidence. A safety answer is restored only when native Laya said apply.
    """
    result={c.factor:c for c in cards}
    if not _ROUTE_REQUEST.search(query):
        return cards
    projected=_FACILITY_PROXIMITY.sub(lambda m:m.group('noun')+(m.group('particle') or '')+' 가까',query)
    if (projected!=query and body['answers']['safety']['choice']=='apply'
            and result['safety'].state!='applied'
            and preview_factor_evidence(projected,'safety')==('positive','apply')):
        result['safety']=ConditionCard(factor='safety',state='applied',direction='maximize',judgment='apply',
            confidence=None,reason='원문의 도움시설 접근성 요청을 보존했습니다.')
    for match in _SHARED_MANY.finditer(query):
        for factor,noun in [('streetlight','가로등'),('cctv','CCTV')]:
            belongs = re.search(r'가로등|조명',match['nouns']) if factor=='streetlight' else re.search(r'CCTV|씨씨티비|방범카메라|감시카메라',match['nouns'],re.I)
            if not belongs or result[factor].state=='applied':
                continue
            # Replacing just this coordinated noun phrase lets the existing
            # last-mention/cancellation guard inspect the full remaining query.
            projected=query[:match.start()]+noun+'가 '+match['predicate']+query[match.end():]
            if preview_factor_evidence(projected,factor)==('positive','apply'):
                result[factor]=ConditionCard(factor=factor,state='applied',direction='maximize',judgment='apply',
                    confidence=None,reason='공유된 서술어로 완성된 가로등·CCTV 요청을 반영했습니다.')
    return [result[c.factor] for c in cards]
