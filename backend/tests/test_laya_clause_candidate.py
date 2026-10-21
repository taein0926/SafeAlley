import pytest
from app.schemas.intent_preview import CARD_ORDER
from app.services.laya_preview_service import map_hybrid_cards
from app.services.laya_clause_candidate import refine_clause_cards

def native(**choices):
 return {'answers':{f:{'type':'choice','choice':choices.get(f,'skip'),'confidence':.99} for f in CARD_ORDER}}

def candidate(q,**choices):
 b=native(**choices);return {c.factor:c for c in refine_clause_cards(b,q,map_hybrid_cards(b,q))}

@pytest.mark.parametrize('facility',['경찰서','지구대','파출소','소방서','응급실'])
def test_proximity_keeps_native_correct_answer(facility):
 q=f'집까지 가로등이 많고 {facility}가 가깝고 계단이 적은 길로 가줘'
 cards=candidate(q,streetlight='apply',safety='apply',stairs='minimize')
 assert cards['safety'].judgment=='apply' and cards['safety'].confidence is None

@pytest.mark.parametrize('q',[
 '경찰서에서 집까지 가로등 많은 길로 가줘',
 '집까지 가로등과 CCTV가 많지 않은 길로 가줘',
 '가로등과 CCTV가 많은 게 무슨 뜻인가요',
 '집까지 가로등과 CCTV가 많고 가로등은 빼고 가줘',
 '집까지 경찰서가 가깝지 않아도 돼',
])
def test_negative_or_unrequested_light_not_forced(q):
 assert candidate(q)['streetlight'].state!='applied'

def test_original_shared_clause():
 cards=candidate('도서관까지 가로등과 CCTV가 많고 안전시설은',streetlight='pending',cctv='apply',safety='pending')
 assert cards['streetlight'].judgment=='apply'
 assert cards['cctv'].judgment=='apply'
 assert cards['safety'].judgment=='pending'

def test_bare_coordination_is_not_completed():
 cards=candidate('학교까지 가로등과 CCTV는',streetlight='pending',cctv='pending')
 assert cards['streetlight'].state!='applied' and cards['cctv'].state!='applied'

def test_later_same_factor_cancellation_wins():
 cards=candidate('학교까지 CCTV와 가로등이 많고 CCTV는 고려하지 마',streetlight='pending',cctv='skip')
 assert cards['streetlight'].state=='applied' and cards['cctv'].state!='applied'

def test_no_positive_safety_if_native_did_not_request():
 assert candidate('경찰서가 가깝고 계단이 적은 길로 가줘')['safety'].state!='applied'
