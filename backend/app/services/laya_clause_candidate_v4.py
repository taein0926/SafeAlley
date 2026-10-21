"""Pilot-only inverse lighting/obstacle permission scope candidate."""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.incomplete_conditions import preview_factor_evidence, _preview_scope

_LOW_LIGHT_AVOID = re.compile(
 r'(?<![가-힣])(?:가로등|조명)(?:은|는|이|가)?\s*(?:적은|없는|부족한)\s*'
 r'(?:곳|구간|길|경로)(?:은|는|을|를)?\s*'
 r'(?:피해서(?!\s*(?:가지\s*마|가고\s*싶지|안))|피해(?:줘|주세요)(?=\s|[.!?]|$)'
 r'|피하고\s*싶(?:어요|습니다|어)(?=\s|[.!?]|$))'
)
_PERMISSION = re.compile(
 r'^\s*(?:은|는|이|가|을|를|도)?\s*'
 r'(?:적어도|많아도|있어도|지나도|건너도|거쳐도)\s*'
 r'(?:괜찮|상관\s*없|무방|돼|되)'
)

def refine_clause_cards_v4(body, query, cards):
 result={c.factor:c for c in cards}
 # Avoiding an explicitly low-light area requests better lighting, unless a
 # later same-factor cancellation or an unfinished instruction supersedes it.
 for match in _LOW_LIGHT_AVOID.finditer(query):
  projected=query[:match.start()]+'가로등이 많은 길로 안내해줘 '+query[match.end():]
  if preview_factor_evidence(projected,'streetlight')==('positive','apply'):
   result['streetlight']=ConditionCard(factor='streetlight',state='applied',judgment='apply',direction='maximize',confidence=None,
    reason='가로등이 적은 구간을 피하려는 명시적 요청을 반영했습니다.')
 for factor in ('stairs','crossing','bridge'):
  scope=_preview_scope(query,factor)
  if scope and _PERMISSION.search(scope[1]):
   result[factor]=ConditionCard(factor=factor,state='not_applied',judgment='skip',confidence=None,
    reason='장애물 구간에 대한 허용 표현을 회피·줄이기 요청으로 확대하지 않았습니다.')
 return [result[c.factor] for c in cards]
