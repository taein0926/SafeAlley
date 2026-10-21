"""Pilot-only clause-scope candidate. Uses no model/network calls."""
import re
from app.schemas.intent_preview import ConditionCard
from app.services.incomplete_conditions import preview_factor_evidence, _PREVIEW_MENTIONS
from app.services.laya_clause_candidate_v2 import _MOVEMENT

_META = re.compile(r'이유|근거|무슨\s*(?:뜻|의미)|의미|정의')
_EXPLAIN = re.compile(r'설명|알려|말해')
_DESIRABLE = {
 'distance':r'최단거리|짧은\s*거리', 'safety':r'안전시설|도움시설',
 'streetlight':r'가로등|조명', 'cctv':r'CCTV|씨씨티비|방범카메라|감시카메라',
}
_TERM=r'(?:'+'|'.join(_DESIRABLE.values())+r')'
_COORDINATED=re.compile(r'(?<![가-힣])(?P<nouns>'+_TERM+r'(?:\s*(?:과|와|및|하고|그리고|,)\s*'+_TERM+r')+)(?:은|는|을|를|이|가|도)?\s*',re.I)
_NEGATIVE_TAIL=re.compile(
 r'^(?:고려하지\s*(?:마|말|않)|신경\s*쓰지\s*마|빼고|제외해|우선하지\s*마'
 r'|(?:적어도|없어도|많지\s*않아도|멀어도|어두워도)\s*(?:괜찮|상관\s*없|돼|되))'
)

def _card(factor, choice, reason):
 return ConditionCard(factor=factor,state='not_applied' if choice=='skip' else 'applied',judgment=choice,
  direction=None if choice=='skip' else choice if choice in {'avoid','minimize'} else 'minimize' if factor=='distance' else 'maximize',
  confidence=None,reason=reason)

def refine_clause_cards_v3(body, query, cards):
 result={c.factor:c for c in cards}
 # Preserve explicit navigation requests when a later sentence asks why.
 # This is a separate clause view for verification only; original input and
 # native model answers remain untouched.
 clauses=re.split(r'(?<=[.!?])\s+|[\n\r]+',query)
 kept=[];removed=[]
 for clause in clauses:
  if kept and _META.search(clause) and _EXPLAIN.search(clause) and not _MOVEMENT.search(clause):
   removed.append(clause)
  else:kept.append(clause)
 if removed and _MOVEMENT.search(' '.join(kept)):
  navigation=' '.join(kept);meta=' '.join(removed)
  for factor,pattern in _PREVIEW_MENTIONS.items():
   if factor=='time' or not pattern.search(meta):continue
   evidence,choice=preview_factor_evidence(navigation,factor)
   if evidence=='positive' and choice in {'apply','avoid','minimize'}:
    result[factor]=_card(factor,choice,'이유 설명 문장과 분리해 앞서 명시한 이동 조건을 보존했습니다.')
 # A shared cancellation/permission predicate belongs to all named desirable
 # factors, not just the final noun. Later explicit same-factor requests win
 # because the existing full-query evidence guard still reads the last mention.
 for match in _COORDINATED.finditer(query):
  if not _NEGATIVE_TAIL.search(query[match.end():]):continue
  for factor,pattern in _DESIRABLE.items():
   if not re.search(pattern,match['nouns'],re.I):continue
   noun={'distance':'최단거리','safety':'안전시설','streetlight':'가로등','cctv':'CCTV'}[factor]
   projected=query[:match.start()]+noun+'은 '+query[match.end():]
   if preview_factor_evidence(projected,factor)[0]=='negative':
    result[factor]=_card(factor,'skip','함께 언급한 조건에 공통으로 적용된 제외·허용 표현을 반영했습니다.')
 return [result[c.factor] for c in cards]
