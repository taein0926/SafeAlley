"""Pilot-only native Laya adapter. Never calls Jev or runs route tools."""
import math
import re
from time import monotonic_ns
import httpx
from app.core.config import get_settings
from app.schemas.intent_preview import CARD_ORDER, ConditionCard, IntentPreviewResponse, IntentPreviewStatus
from app.services.jev_preview_service import PreviewUnavailable, build_request, parse_decisions
from app.services.incomplete_conditions import preview_factor_evidence, incomplete_condition_factors
from app.services.laya_departure_clock import explicit_departure_clock
from app.services.weather_service import resolve_route_time
from app.services.laya_clause_candidate import refine_clause_cards
from app.services.laya_clause_candidate_v2 import refine_clause_cards_v2
from app.services.laya_clause_candidate_v3 import refine_clause_cards_v3
from app.services.laya_clause_candidate_v4 import refine_clause_cards_v4
from app.services.laya_clause_candidate_v5 import refine_clause_cards_v5
from app.services.laya_clause_candidate_v6 import refine_clause_cards_v6

ALLOWED={f:{'apply','skip','pending'} for f in CARD_ORDER}
ALLOWED.update(stairs={'avoid','minimize','skip','pending'},crossing={'avoid','minimize','skip','pending'},
 bridge={'apply','avoid','minimize','skip','pending'},time={'day','night','skip','pending'})

_OBSTACLES = {'stairs': r'계단|층계', 'crossing': r'횡단보도|건널목', 'bridge': r'육교|고가\s*보도'}
_OBSTACLE_NOUN = r'(?:계단|층계|횡단보도|건널목|육교|고가\s*보도)'
# Only a local noun list followed immediately by a completed avoidance cue.
# No arbitrary text between the nouns and predicate: do not borrow another
# clause's direction, a place name, or a partial "피"/negated "피하지".
_AVOID_LIST = re.compile(
 r'(?<![가-힣])(?P<nouns>' + _OBSTACLE_NOUN
 + r'(?:\s*(?:와|과|및|하고|,)\s*' + _OBSTACLE_NOUN + r')*)'
 + r'\s*(?:은|는|을|를)?\s*(?:피하고|피해서|피해(?:서)?|피하자|피해줘)(?=\s|[.!?,]|$)'
)
_REPLACEMENT_ROUTE = re.compile(
 r'(?<![가-힣])(?P<avoided>' + _OBSTACLE_NOUN + r')(?:은|는|을|를)?\s*대신\s*'
 r'(?P<alternative>' + _OBSTACLE_NOUN + r'|지하도|평지|인도|보도)'
 r'(?P<action>(?:으)?로\s*(?:갈래(?:요)?|갈게(?:요)?|가줘|가주세요|가고\s*싶어(?:요)?|가자|안내해줘)'
 r'|(?:을|를)?\s*(?:이용할래(?:요)?|이용해줘|거쳐\s*갈래(?:요)?))(?=\s|[.!?,]|$)'
)

def explicit_pilot_choice(query, factor):
 """Pilot-only recovery of clear source requests, not model training."""
 if factor not in {'distance','stairs','crossing','bridge'}:
  return None
 evidence, choice = preview_factor_evidence(query, factor)
 if evidence == 'positive':
  return choice
 if evidence == 'negative':
  return None
 if factor in _OBSTACLES:
  # A 대신 B로 갈래 is an explicit exclusion of A, not an absence of
  # preference. Only accept a completed local movement clause, never a bare
  # noun list, a question about meanings, or a destination containing A.
  for match in _REPLACEMENT_ROUTE.finditer(query):
   if re.fullmatch(_OBSTACLES[factor],match.group('avoided')):
    if match.group('avoided')==match.group('alternative'):
     continue
    # Do not restore an older exclusion after the same obstacle is mentioned
    # again with a correction. The existing evidence guard handles that scope.
    if re.search(_OBSTACLES[factor],query[match.end():]):
     continue
    return 'avoid'
  for match in _AVOID_LIST.finditer(query):
   if re.search(_OBSTACLES[factor], match.group('nouns')):
    return 'avoid'
 return None

def preview_status():
 s=get_settings();configured=bool(s.laya_preview_url);available=False
 if s.laya_preview_enabled and configured:
  try:
   r=httpx.get(s.laya_preview_url+'/health',timeout=2);r.raise_for_status()
   available=r.json().get('checkpoint_sha256')==s.laya_checkpoint_sha256
  except (httpx.HTTPError,ValueError,AttributeError):pass
 return IntentPreviewStatus(enabled=s.laya_preview_enabled,configured=configured,available=available)

def map_cards(body,query=None):
 answers=body.get('answers')
 if not isinstance(answers,dict) or set(answers)!=set(CARD_ORDER):raise PreviewUnavailable('Laya 카드 응답이 올바르지 않습니다.')
 cards=[]
 for f in CARD_ORDER:
  a=answers[f]
  if not isinstance(a,dict) or a.get('type')!='choice' or not isinstance(a.get('choice'),str) or a['choice'] not in ALLOWED[f]:raise PreviewUnavailable('Laya 조건 판단값이 올바르지 않습니다.')
  choice=a['choice'];confidence=a.get('confidence')
  if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0<=confidence<=1:raise PreviewUnavailable('Laya 신뢰도 형식이 올바르지 않습니다.')
  state='not_applied' if choice=='skip' else 'analyzing' if choice=='pending' else 'applied'
  reason=None
  if query is not None:
   evidence,_ = preview_factor_evidence(query, f)
   explicit = explicit_pilot_choice(query, f)
   # A positive native prediction cannot override a scoped source rejection
   # such as "계단 피하지 않고 건널목 피해서". Use the existing evidence
   # parser (including its last-mention scope), not another negation regex.
   if evidence == 'negative':
    if choice != 'skip':confidence=None
    choice, state = 'skip', 'not_applied'
    reason='원문에서 해당 조건의 적용을 부정하여 미적용했습니다.'
   elif explicit is not None and explicit != choice:
    choice, state, confidence = explicit, 'applied', None
    reason='원문에 명확하게 표현된 거리·장애물 선호를 반영했습니다.'
  # Safety alone must not be inferred from lighting/CCTV. Reuse the existing
  # source-evidence guard; never alter the underlying model or other cards.
  if f=='safety' and query is not None:
   evidence,_=preview_factor_evidence(query,'safety')
   if evidence in {'absent','negative'}:
    if choice!='skip':confidence=None
    state,choice='not_applied','skip'
    reason='원문에 안전시설 선호 요청이 없거나 제외되어 미적용했습니다.'
   elif evidence in {'incomplete','mentioned'}:
    if choice!='pending':confidence=None
    state,choice='analyzing','pending'
    reason='안전시설 요청의 방향을 아직 확인 중입니다.'
  direction=None;period=None
  if state=='applied':
   if f=='time':period=choice
   else:direction=choice if choice in {'avoid','minimize'} else 'minimize' if f=='distance' else 'maximize'
  cards.append(ConditionCard(factor=f,state=state,judgment=choice,confidence=confidence,direction=direction,period=period,reason=reason))
 return cards

def map_hybrid_cards(body, query):
 """Tested composition plus pilot-only explicit departure clock normalization.

 Keep pilot corrections and scoped source rejections; import only existing
 unfinished and positive/applied branches. Confidence-only branches cannot
 replace the pilot result. Explicit clocks use the final routing day/night policy.
 """
 cards=map_cards(body,query=query)
 payload=build_request(query,'laya-local-validation-only')
 existing={c.factor:c for c in parse_decisions(payload,body,.7)}
 unfinished=incomplete_condition_factors(query)
 metrics={'distance':'distance_m','safety':'safety_score','streetlight':'streetlight_score',
          'cctv':'cctv_score','stairs':'stairs_distance_m','crossing':'crosswalk_count','bridge':'pedestrian_bridge_count'}
 combined=[]
 for card in cards:
  evidence,_=preview_factor_evidence(query,card.factor)
  incomplete=metrics.get(card.factor) in unfinished or evidence=='incomplete'
  inc=existing[card.factor] if incomplete else card
  if not incomplete and evidence=='positive' and existing[card.factor].state=='applied':
   combined.append(existing[card.factor])
  else:combined.append(inc)
 status, clock = explicit_departure_clock(query)
 if status != 'absent':
  period = ('night' if resolve_route_time(clock).is_night else 'day') if status=='apply' else None
  time_card = ConditionCard(factor='time',state='applied' if status=='apply' else 'not_applied' if status=='skip' else 'analyzing',
   judgment=period or ('skip' if status=='skip' else 'pending'),period=period,confidence=None,
   reason='명시된 출발 시각에 최종 경로와 같은 주간·야간 기준을 적용했습니다.' if status=='apply'
    else '도착 시각만 지정되어 출발 시간대로 적용하지 않았습니다.' if status=='skip'
    else '출발 시각이 모호하거나 올바른 시각으로 완성되지 않았습니다.')
  combined=[time_card if c.factor=='time' else c for c in combined]
 return combined

def analyze_preview(query):
 s=get_settings()
 if not s.laya_preview_enabled:raise PreviewUnavailable('Laya 시범 분석이 비활성입니다.')
 query=query.strip();version=monotonic_ns()%1_000_000_000
 try:
  r=httpx.post(s.laya_preview_url+'/analyze',json=dict(query=query,version=version),timeout=15);r.raise_for_status();body=r.json()
 except (httpx.HTTPError,ValueError) as exc:raise PreviewUnavailable('Laya 연결 실패: Jev로 대체 호출하지 않습니다.') from exc
 if not isinstance(body,dict) or body.get('checkpoint_sha256')!=s.laya_checkpoint_sha256:raise PreviewUnavailable('고정 Laya 모델과 일치하지 않습니다.')
 if body.get('version')!=version or body.get('query')!=query:raise PreviewUnavailable('Laya 응답의 입력 버전이 다릅니다.')
 cards=map_hybrid_cards(body,query=query)
 # Selected by sealed paired comparison (2026-10-21). Retain the frozen clause
 # refinements; scoped negative evidence is enforced in map_cards above.
 cards=refine_clause_cards(body,query,cards)
 cards=refine_clause_cards_v2(body,query,cards)
 cards=refine_clause_cards_v3(body,query,cards)
 cards=refine_clause_cards_v4(body,query,cards)
 cards=refine_clause_cards_v5(body,query,cards)
 return IntentPreviewResponse(query=query,model='laya-'+s.laya_checkpoint_sha256[:12],conditions=refine_clause_cards_v6(body,query,cards))
