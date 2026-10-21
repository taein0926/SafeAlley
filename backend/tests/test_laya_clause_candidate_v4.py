import pytest
from app.schemas.intent_preview import CARD_ORDER
from app.services.laya_preview_service import map_hybrid_cards
from app.services.laya_clause_candidate import refine_clause_cards
from app.services.laya_clause_candidate_v2 import refine_clause_cards_v2
from app.services.laya_clause_candidate_v3 import refine_clause_cards_v3
from app.services.laya_clause_candidate_v4 import refine_clause_cards_v4

def result(q,**choices):
 b={'answers':{f:{'type':'choice','choice':choices.get(f,'skip'),'confidence':.99} for f in CARD_ORDER}}
 c=refine_clause_cards(b,q,map_hybrid_cards(b,q));c=refine_clause_cards_v2(b,q,c);c=refine_clause_cards_v3(b,q,c)
 return {x.factor:x for x in refine_clause_cards_v4(b,q,c)}

@pytest.mark.parametrize('q',[
 '공원까지 가로등이 적은 곳은 피해서 가고 싶어요',
 '학교까지 조명이 없는 구간은 피해주세요',
 '집까지 가로등이 부족한 길은 피하고 싶어요',
])
def test_low_lighting_avoidance(q):
 assert result(q)['streetlight'].judgment=='apply'

@pytest.mark.parametrize('q',[
 '가로등이 적은 곳은 피하지 않아도 돼',
 '가로등이 없는 구간은 피하고 싶지 않아',
 '가로등이 적은 곳은 피해서 가지 마',
 '학교까지 가로등이 적은 곳은 피',
 '가로등이 적은 곳에서 역까지 가줘',
 '가로등이 적은 곳은 피해서 가줘. 가로등은 고려하지 마',
])
def test_no_unfinished_or_cancelled_inverse_recovery(q):
 assert result(q)['streetlight'].state!='applied'

@pytest.mark.parametrize('noun,factor',[('계단','stairs'),('횡단보도','crossing'),('육교','bridge')])
def test_permission_not_preference(noun,factor):
 c=result(f'학교까지 {noun}은 적어도 괜찮아',**{factor:'minimize'})
 assert c[factor].judgment=='skip'

def test_last_positive_request_wins_over_earlier_permission():
 c=result('계단은 많아도 괜찮아. 그래도 계단 없는 길로 안내해줘',stairs='avoid')
 assert c['stairs'].judgment=='avoid'

def test_clear_minimize_is_not_permission():
 c=result('계단은 적게 지나고 싶고 CCTV 많은 길로 가줘',stairs='minimize',cctv='apply')
 assert c['stairs'].judgment=='minimize' and c['cctv'].judgment=='apply'

def test_permission_does_not_cancel_other_card():
 c=result('계단은 적어도 괜찮아. CCTV 많은 길로 가줘',stairs='minimize',cctv='apply')
 assert c['stairs'].judgment=='skip' and c['cctv'].judgment=='apply'
